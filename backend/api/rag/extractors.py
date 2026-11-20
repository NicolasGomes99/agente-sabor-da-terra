import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

INDEXABLE_EXTENSIONS = frozenset({".txt", ".csv"})

_ID_COLUMN_CANDIDATES: tuple[str, ...] = (
    "id_transacao",
    "lote_id",
    "id",
    "codigo",
    "registro_id",
    "produto",
)

_BORDER_LINE_RE = re.compile(r"^[=\-_]{5,}$")
_SECTION_HEADER_RE = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s/()\-]{2,}:$")


class DocumentExtractionError(ValueError):
    """Erro ao extrair ou validar trechos/registros de um documento TXT ou CSV."""


@dataclass(frozen=True)
class ExtractedChunk:
    chunk_key: str
    chunk_index: int
    content: str
    record_id: str | None = None
    record_fields: dict[str, str] | None = None


def _normalize_identifier(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_only.strip().lower()


def _basename(filename: str) -> str:
    normalized = filename.replace("\\", "/").strip()
    return PurePosixPath(normalized).name


def get_document_extension(filename: str) -> str:
    name = _basename(filename)
    dot_index = name.rfind(".")
    if dot_index <= 0:
        return ""
    return name[dot_index:].lower()


def is_indexable_document(filename: str) -> bool:
    return get_document_extension(filename) in INDEXABLE_EXTENSIONS


def _decode_utf8(raw_bytes: bytes, *, filename: str) -> str:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentExtractionError(
            f"O arquivo '{_basename(filename)}' não está codificado em UTF-8 válido."
        ) from error
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_header_context(text: str, *, max_header_chars: int = 550) -> str:
    """Extrai cabeçalho e metadados iniciais para preservar contexto entre trechos."""
    lines = text.split("\n")
    collected: list[str] = []
    total_chars = 0
    seen_non_empty = False
    blank_blocks_after_title = 0

    for raw_line in lines:
        stripped = raw_line.strip()
        if _BORDER_LINE_RE.match(stripped):
            continue
        if not stripped:
            if seen_non_empty:
                blank_blocks_after_title += 1
                # Mantém título + bloco inicial de identificação/validade/partes
                if blank_blocks_after_title >= 3 and total_chars >= 180:
                    break
            continue

        seen_non_empty = True
        # Para ao chegar em seções longas de corpo depois de já coletar o cabeçalho
        if (
            blank_blocks_after_title >= 2
            and total_chars >= 180
            and _SECTION_HEADER_RE.match(stripped)
            and not any(
                token in _normalize_identifier(stripped)
                for token in (
                    "dados do produtor",
                    "dados do estabelecimento",
                    "contratante",
                    "contratada",
                    "comprador",
                    "vigencia",
                    "denominacao",
                )
            )
        ):
            break

        line_to_add = stripped
        if total_chars + len(line_to_add) + 1 > max_header_chars:
            break
        collected.append(line_to_add)
        total_chars += len(line_to_add) + 1

    return "\n".join(collected).strip()


def _split_into_sections(text: str) -> list[str]:
    raw_blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    sections: list[str] = []
    for block in raw_blocks:
        cleaned_lines = [
            line.rstrip()
            for line in block.split("\n")
            if not _BORDER_LINE_RE.match(line.strip())
        ]
        cleaned_block = "\n".join(cleaned_lines).strip()
        if cleaned_block:
            sections.append(cleaned_block)
    return sections


def _split_oversized_section(section: str, *, max_body_chars: int) -> list[str]:
    lines = [line.rstrip() for line in section.split("\n") if line.strip()]
    if not lines:
        return []

    pieces: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        if len(line) > max_body_chars:
            if current:
                pieces.append("\n".join(current))
                current = []
                current_len = 0
            # Quebra por palavras sem cortar tokens no meio
            words = line.split()
            buf: list[str] = []
            buf_len = 0
            for word in words:
                addition = len(word) + (1 if buf else 0)
                if buf and buf_len + addition > max_body_chars:
                    pieces.append(" ".join(buf))
                    buf = [word]
                    buf_len = len(word)
                else:
                    buf.append(word)
                    buf_len += addition
            if buf:
                pieces.append(" ".join(buf))
            continue

        addition = len(line) + (1 if current else 0)
        if current and current_len + addition > max_body_chars:
            pieces.append("\n".join(current))
            # Sobreposição de 1 linha para preservar continuidade semântica
            overlap = current[-1]
            if len(overlap) + 1 + len(line) <= max_body_chars:
                current = [overlap, line]
                current_len = len(overlap) + 1 + len(line)
            else:
                current = [line]
                current_len = len(line)
        else:
            current.append(line)
            current_len += addition

    if current:
        pieces.append("\n".join(current))
    return pieces


def extract_text_chunks(
    raw_bytes: bytes,
    *,
    filename: str,
    max_chars: int = 1600,
) -> list[ExtractedChunk]:
    """Extrai trechos contextuais de um arquivo TXT preservando cabeçalho e seções."""
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200.")

    name = _basename(filename)
    decoded = _decode_utf8(raw_bytes, filename=name).strip()
    if not decoded:
        raise DocumentExtractionError(
            f"O arquivo textual '{name}' está vazio e não possui conteúdo para indexação."
        )

    sections = _split_into_sections(decoded)
    if not sections:
        raise DocumentExtractionError(
            f"O arquivo textual '{name}' não possui conteúdo útil para indexação."
        )

    full_body = "\n\n".join(sections)
    # Documentos curtos (ex.: maioria das certificações e fichas) permanecem íntegros em 1 trecho.
    if len(full_body) <= max_chars + 250:
        return [
            ExtractedChunk(
                chunk_key="chunk:0",
                chunk_index=0,
                content=f"Documento: {name}\n{full_body}",
            )
        ]

    header_context = _extract_header_context(decoded)
    header_prefix = (
        f"Documento: {name}\n[Contexto do documento]\n{header_context}\n---\n"
        if header_context
        else f"Documento: {name}\n"
    )
    max_body_chars = max(300, max_chars - len(header_prefix))

    normalized_sections: list[str] = []
    for section in sections:
        if len(section) <= max_body_chars:
            normalized_sections.append(section)
        else:
            normalized_sections.extend(
                _split_oversized_section(section, max_body_chars=max_body_chars)
            )

    grouped_bodies: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for section in normalized_sections:
        addition = len(section) + (2 if current_parts else 0)
        if current_parts and current_len + addition > max_body_chars:
            grouped_bodies.append("\n\n".join(current_parts))
            current_parts = [section]
            current_len = len(section)
        else:
            current_parts.append(section)
            current_len += addition

    if current_parts:
        grouped_bodies.append("\n\n".join(current_parts))

    chunks: list[ExtractedChunk] = []
    for idx, body in enumerate(grouped_bodies):
        if idx == 0:
            content = f"Documento: {name}\n{body}"
        else:
            content = f"{header_prefix}{body}"
        chunks.append(
            ExtractedChunk(
                chunk_key=f"chunk:{idx}",
                chunk_index=idx,
                content=content,
            )
        )
    return chunks


def _detect_csv_delimiter(sample_text: str) -> str:
    first_line = next(
        (line for line in sample_text.split("\n") if line.strip()),
        "",
    )
    if ";" in first_line and "," not in first_line:
        return ";"
    return ","


def _select_id_column(headers: list[str]) -> str | None:
    normalized_map = {_normalize_identifier(header): header for header in headers}
    for candidate in _ID_COLUMN_CANDIDATES:
        if candidate in normalized_map:
            return normalized_map[candidate]
    return None


def extract_csv_records(
    raw_bytes: bytes,
    *,
    filename: str,
) -> list[ExtractedChunk]:
    """Extrai cada registro de CSV preservando nomes de colunas, valores originais e ID."""
    name = _basename(filename)
    decoded = _decode_utf8(raw_bytes, filename=name)
    if not decoded.strip():
        raise DocumentExtractionError(
            f"O arquivo CSV '{name}' está vazio e não possui registros para indexação."
        )

    delimiter = _detect_csv_delimiter(decoded)
    reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration as error:
        raise DocumentExtractionError(
            f"O arquivo CSV '{name}' não possui cabeçalho."
        ) from error

    headers = [header.strip() for header in raw_headers]
    if not headers or any(not header for header in headers):
        raise DocumentExtractionError(
            f"O arquivo CSV '{name}' possui cabeçalho inválido ou coluna sem nome."
        )
    if len(set(headers)) != len(headers):
        raise DocumentExtractionError(
            f"O arquivo CSV '{name}' possui nomes de colunas duplicados."
        )

    id_column = _select_id_column(headers)
    seen_record_ids: set[str] = set()
    records: list[ExtractedChunk] = []

    for row_number, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) != len(headers):
            raise DocumentExtractionError(
                f"O arquivo CSV '{name}' possui número de colunas incompatível "
                f"na linha {row_number + 1} (esperado {len(headers)}, encontrado {len(row)})."
            )

        # Preserva exatamente o nome das colunas e os valores originais (sem conversões).
        fields: dict[str, str] = {
            header: value for header, value in zip(headers, row, strict=True)
        }

        raw_record_id = fields.get(id_column, "").strip() if id_column else ""
        if raw_record_id and raw_record_id not in seen_record_ids:
            record_id = raw_record_id
        elif raw_record_id:
            record_id = f"{raw_record_id}#{row_number}"
        else:
            record_id = f"linha-{row_number}"
        seen_record_ids.add(record_id)

        content_lines = [f"Documento: {name} | Registro: {record_id}"]
        for col, val in fields.items():
            if val != "":
                content_lines.append(f"{col}: {val}")

        records.append(
            ExtractedChunk(
                chunk_key=f"record:{record_id}",
                chunk_index=len(records),
                content="\n".join(content_lines),
                record_id=record_id,
                record_fields=fields,
            )
        )

    if not records:
        raise DocumentExtractionError(
            f"O arquivo CSV '{name}' não possui linhas de dados para indexação."
        )

    return records


def extract_document_chunks(
    raw_bytes: bytes,
    *,
    filename: str,
    max_text_chars: int = 1600,
) -> list[ExtractedChunk]:
    """Despacha a extração de conteúdo para arquivos TXT ou CSV."""
    extension = get_document_extension(filename)
    if extension == ".txt":
        return extract_text_chunks(raw_bytes, filename=filename, max_chars=max_text_chars)
    if extension == ".csv":
        return extract_csv_records(raw_bytes, filename=filename)
    raise DocumentExtractionError(
        f"Formato de arquivo não suportado para indexação documental: '{_basename(filename)}'."
    )
