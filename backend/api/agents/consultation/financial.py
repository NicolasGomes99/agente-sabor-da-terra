import calendar
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from ..config import to_pernambuco_date
from .schemas.financial import (
    FinancialCalculationBucket,
    FinancialSummaryCalculation,
    ProducerMatchCandidate,
    format_brl_currency,
)
from .schemas.input import ConsultationSourceItem, SourceKind

FINANCIAL_SOURCE_FILENAME = "financeiro.csv"
FINANCIAL_TOOL_NAME = "calcular_resumo_financeiro_produtor"

_PRODUCER_CODE_RE = re.compile(r"\b(P\d{2,4})\b", re.IGNORECASE)
_HISTORY_BLOCK_RE = re.compile(
    r"<historico_sessao_atual>.*?</historico_sessao_atual>",
    re.DOTALL,
)
_ISO_RANGE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(?:a|at[ée]|e|-)\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_BR_RANGE_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s*(?:a|at[ée]|e|-)\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_ISO_MONTH_RE = re.compile(r"(?<!\d-)(\d{4})-(\d{2})(?!-\d{2})\b")
_BR_MONTH_RE = re.compile(r"(?<!\d/)(\d{2})/(\d{4})(?!\d)")

_MONTH_NAMES: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_MONTH_NAME_RE = re.compile(
    r"\b(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)(?:\s*(?:de|/)\s*(\d{4}))?\b",
    re.IGNORECASE,
)

_EXPLICIT_FINANCIAL_SUMMARY_TERMS: tuple[str, ...] = (
    "resumo financeiro",
    "pendencias financeiras",
    "pendencia financeira",
    "saldo financeiro",
    "financeiro.csv",
    "fin-2026",
    "faturamento",
    "repasse",
)

_DOCUMENT_NON_FINANCIAL_PHRASES: tuple[str, ...] = (
    "condicao de pagamento",
    "condicoes de pagamento",
    "forma de pagamento",
    "formas de pagamento",
    "prazo de pagamento",
    "preco de venda",
    "precos de venda",
    "tabela de precos",
)

_CONTEXTUAL_FINANCIAL_TERMS: tuple[str, ...] = (
    "financeir",
    "vendas",
    "pagamentos",
    "a vencer",
    "a receber",
    "vencida",
    "vencidas",
    "vencido",
    "vencidos",
    "resumo",
)

_PRODUCER_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?<!\bessa\s)(?<!\besse\s)(?<!\besta\s)(?<!\beste\s)"
        r"(?<!\baquela\s)(?<!\baquele\s)"
        r"\bprodutor(?:a)?\s+(?:de|da|do)?\s*"
        r"([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\s.-]{1,80}?)"
        r"(?=\s+(?:em|para|no|na|entre|com|durante|ref(?:er[êe]ncia)?)\b|[?!.,;]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:resumo(?:\s+financeiro)?|vendas(?:\s+e\s+pend[êe]ncias(?:\s+financeiras)?)?|"
        r"pagamentos(?:\s+registrados)?|pend[êe]ncias(?:\s+financeiras)?)\s+"
        r"(?:de|da|do)\s+"
        r"([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\s.-]{1,80}?)"
        r"(?=\s+(?:em|para|no|na|entre|com|durante|ref(?:er[êe]ncia)?)\b|[?!.,;]|$)",
        re.IGNORECASE,
    ),
)

_NON_PRODUCER_LEADING_TOKENS: set[str] = {
    "produtor",
    "produtora",
    "de",
    "da",
    "do",
    "das",
    "dos",
}

_NON_PRODUCER_FIRST_TOKENS: set[str] = {
    "tem",
    "teve",
    "possui",
    "recebeu",
    "vendeu",
    "esta",
    "foi",
    "vai",
    "deve",
    "precisa",
    "ficou",
    "pode",
    "que",
    "qual",
    "quais",
    "quanto",
    "essa",
    "esse",
    "este",
}


@runtime_checkable
class FinancialRecordsProvider(Protocol):
    """Contrato explícito para recuperação exaustiva de registros de financeiro.csv no RAG.

    Diferente de `sources` (que pode resultar de busca semântica limitada por relevância),
    este provedor garante acesso a todos os registros financeiros elegíveis indexados.
    """

    def list_all_financial_records(self) -> Sequence[ConsultationSourceItem | Any]:
        ...


class InMemoryFinancialRecordsProvider:
    """Provedor em memória do contrato exaustivo para testes e carga direta do índice."""

    def __init__(self, records: Sequence[ConsultationSourceItem | Any]) -> None:
        self._records = list(records)

    def list_all_financial_records(self) -> list[ConsultationSourceItem | Any]:
        return list(self._records)


def resolve_exhaustive_financial_records(
    financial_records_provider: FinancialRecordsProvider | None = None,
    financial_records: Sequence[ConsultationSourceItem | Any] | None = None,
) -> list[ConsultationSourceItem | Any] | None:
    """Obtém a coleção exaustiva de registros financeiros quando o contrato estiver presente."""
    if financial_records_provider is not None:
        return list(financial_records_provider.list_all_financial_records())
    if financial_records is not None:
        return list(financial_records)
    return None


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    return " ".join(without_accents.lower().strip().split())


def _tokenize_name(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalize_text(value))


def is_financial_csv_document(document_name: str | None) -> bool:
    """Verifica explicitamente se o arquivo de origem é `financeiro.csv`."""
    if not document_name:
        return False
    basename = document_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip().lower()
    return basename == FINANCIAL_SOURCE_FILENAME


@dataclass(frozen=True)
class _ParsedFinancialRow:
    source_id: str
    document_name: str
    transaction_id: str
    producer_id: str
    producer_name: str | None
    transaction_type: str
    amount: Decimal
    transaction_date: date
    due_date: date | None
    payment_date: date | None


def _parse_optional_date(raw: Any) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return to_pernambuco_date(text)


def _parse_content_kv(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for sep in (";", ",", "\n"):
        if sep in content and "=" in content:
            for part in content.split(sep):
                if "=" in part:
                    k, v = part.split("=", maxsplit=1)
                    fields[k.strip()] = v.strip()
            if fields:
                return fields
    return fields


def to_consultation_source_item(
    item: ConsultationSourceItem | Any,
) -> ConsultationSourceItem | None:
    """Converte um item/DocumentChunk financeiro em ConsultationSourceItem para citação."""
    if isinstance(item, ConsultationSourceItem):
        return item

    if isinstance(item, dict):
        doc_name = str(item.get("document_name") or "").strip()
        if not doc_name:
            return None
        record_fields = item.get("record_fields")
        fields_dict = dict(record_fields) if isinstance(record_fields, dict) else None
        raw_content = str(item.get("content") or "").strip()
        if not raw_content and fields_dict:
            raw_content = "; ".join(f"{k}={v}" for k, v in fields_dict.items())
        record_id = item.get("record_id") or item.get("reference_label") or (
            fields_dict.get("id_transacao") if fields_dict else None
        )
        source_id = str(item.get("source_id") or item.get("id") or record_id or "").strip()
        if not source_id or not raw_content:
            return None
        doc_id = item.get("document_id")
        return ConsultationSourceItem(
            source_id=source_id,
            source_kind=SourceKind.FINANCIAL_RECORD,
            document_id=str(doc_id) if doc_id is not None else None,
            document_name=doc_name,
            reference_label=str(record_id) if record_id is not None else None,
            record_id=str(record_id) if record_id is not None else None,
            record_fields=fields_dict,
            content=raw_content,
        )

    doc_obj = getattr(item, "document", None)
    doc_name = str(
        getattr(item, "document_name", None)
        or getattr(doc_obj, "original_filename", None)
        or ""
    ).strip()
    if not doc_name:
        return None
    record_fields = getattr(item, "record_fields", None)
    fields_dict = dict(record_fields) if isinstance(record_fields, dict) else None
    raw_content = str(getattr(item, "content", "") or "").strip()
    if not raw_content and fields_dict:
        raw_content = "; ".join(f"{k}={v}" for k, v in fields_dict.items())
    record_id = (
        getattr(item, "record_id", None)
        or getattr(item, "reference_label", None)
        or (fields_dict.get("id_transacao") if fields_dict else None)
    )
    source_id = str(
        getattr(item, "source_id", None) or getattr(item, "id", None) or record_id or ""
    ).strip()
    if not source_id or not raw_content:
        return None
    doc_id = getattr(item, "document_id", None)
    return ConsultationSourceItem(
        source_id=source_id,
        source_kind=SourceKind.FINANCIAL_RECORD,
        document_id=str(doc_id) if doc_id is not None else None,
        document_name=doc_name,
        reference_label=str(record_id) if record_id is not None else None,
        record_id=str(record_id) if record_id is not None else None,
        record_fields=fields_dict,
        content=raw_content,
    )


def _extract_financial_row(item: ConsultationSourceItem | Any) -> _ParsedFinancialRow | None:
    if isinstance(item, ConsultationSourceItem):
        if item.source_kind in {SourceKind.LOT_RECORD, SourceKind.PRODUCER_RECORD}:
            return None
        if not is_financial_csv_document(item.document_name):
            return None
        source_id = item.source_id
        document_name = item.document_name
        raw_fields = (
            dict(item.record_fields)
            if item.record_fields
            else _parse_content_kv(item.content)
        )
        fallback_tx_id = item.record_id or item.reference_label
    elif isinstance(item, dict):
        raw_kind = str(item.get("source_kind") or "").strip().lower()
        if raw_kind in {SourceKind.LOT_RECORD.value, SourceKind.PRODUCER_RECORD.value}:
            return None
        raw_doc_name = item.get("document_name")
        if not is_financial_csv_document(str(raw_doc_name) if raw_doc_name is not None else None):
            return None
        document_name = str(raw_doc_name).strip()
        source_id = str(item.get("source_id") or item.get("id") or "")
        raw_fields = dict(
            item.get("record_fields") or _parse_content_kv(str(item.get("content") or ""))
        )
        fallback_tx_id = (
            item.get("record_id")
            or item.get("reference_label")
            or raw_fields.get("id_transacao")
        )
    else:
        doc_obj = getattr(item, "document", None)
        raw_doc_name = (
            getattr(item, "document_name", None)
            or getattr(doc_obj, "original_filename", None)
        )
        if not is_financial_csv_document(str(raw_doc_name) if raw_doc_name is not None else None):
            return None
        document_name = str(raw_doc_name).strip()
        source_id = str(getattr(item, "source_id", None) or getattr(item, "id", ""))
        record_fields = getattr(item, "record_fields", None)
        content_str = str(getattr(item, "content", "") or "")
        raw_fields = dict(record_fields) if record_fields else _parse_content_kv(content_str)
        fallback_tx_id = getattr(item, "record_id", None) or getattr(
            item, "reference_label", None
        )

    tx_id = str(raw_fields.get("id_transacao") or fallback_tx_id or "").strip()
    prod_id = str(raw_fields.get("produtor_id") or "").strip()
    raw_amount = raw_fields.get("valor_total")
    raw_tx_date = raw_fields.get("data") or raw_fields.get("data_transacao")

    if not tx_id or not prod_id or raw_amount is None or not raw_tx_date:
        return None

    try:
        amount = Decimal(str(raw_amount).strip())
        tx_date = to_pernambuco_date(str(raw_tx_date).strip())
    except Exception:  # noqa: BLE001
        return None

    return _ParsedFinancialRow(
        source_id=source_id or tx_id,
        document_name=document_name,
        transaction_id=tx_id,
        producer_id=prod_id,
        producer_name=(
            str(raw_fields.get("produtor_nome")).strip()
            if raw_fields.get("produtor_nome")
            else None
        ),
        transaction_type=str(raw_fields.get("tipo") or "venda").strip().lower(),
        amount=amount,
        transaction_date=tx_date,
        due_date=_parse_optional_date(raw_fields.get("data_vencimento")),
        payment_date=_parse_optional_date(raw_fields.get("data_pagamento")),
    )


def resolve_period_bounds(
    period: str | None = None,
    *,
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    fallback_reference_date: date | None = None,
) -> tuple[date, date]:
    if period_start is not None and period_end is not None:
        start = to_pernambuco_date(period_start)
        end = to_pernambuco_date(period_end)
        if end < start:
            raise ValueError("period_end must be greater than or equal to period_start.")
        return start, end

    if period:
        cleaned = period.strip()
        if len(cleaned) == 7 and cleaned[4] == "-":
            year, month = int(cleaned[:4]), int(cleaned[5:7])
        elif len(cleaned) == 7 and cleaned[2] == "/":
            month, year = int(cleaned[:2]), int(cleaned[3:7])
        else:
            single = to_pernambuco_date(cleaned)
            return single, single
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    if fallback_reference_date is not None:
        last_day = calendar.monthrange(
            fallback_reference_date.year,
            fallback_reference_date.month,
        )[1]
        return (
            date(fallback_reference_date.year, fallback_reference_date.month, 1),
            date(fallback_reference_date.year, fallback_reference_date.month, last_day),
        )

    raise ValueError("Either (period_start, period_end) or period must be provided.")


def _extract_producer_from_text(text: str) -> str | None:
    code_match = _PRODUCER_CODE_RE.search(text)
    if code_match:
        return code_match.group(1).upper()

    for pattern in _PRODUCER_NAME_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1).strip(" .,-")
            tokens = _tokenize_name(candidate)
            while tokens and tokens[0] in _NON_PRODUCER_LEADING_TOKENS:
                tokens = tokens[1:]
            if (
                not tokens
                or tokens[0] in _NON_PRODUCER_FIRST_TOKENS
                or all(t in _MONTH_NAMES or t.isdigit() for t in tokens)
            ):
                continue
            cleaned_words = candidate.split()
            while (
                cleaned_words
                and _normalize_text(cleaned_words[0]) in _NON_PRODUCER_LEADING_TOKENS
            ):
                cleaned_words = cleaned_words[1:]
            if cleaned_words:
                return " ".join(cleaned_words)
    return None


def is_financial_consultation_query(question: str) -> bool:
    """Identifica se a pergunta do funcionário solicita resumo ou cálculo financeiro."""
    current = _HISTORY_BLOCK_RE.sub("", question).strip()
    normalized = _normalize_text(current)
    if any(term in normalized for term in _EXPLICIT_FINANCIAL_SUMMARY_TERMS):
        return True
    if any(phrase in normalized for phrase in _DOCUMENT_NON_FINANCIAL_PHRASES):
        return False
    has_contextual_term = any(
        term in normalized for term in _CONTEXTUAL_FINANCIAL_TERMS
    )
    if not has_contextual_term:
        return False
    has_producer_signal = bool(
        _PRODUCER_CODE_RE.search(current)
        or "produtor" in normalized
        or "produtora" in normalized
        or _extract_producer_from_text(current) is not None
    )
    return has_producer_signal


def _parse_br_date(raw: str) -> date:
    day_str, month_str, year_str = raw.split("/")
    return date(int(year_str), int(month_str), int(day_str))


def extract_financial_query_params(
    question: str,
    *,
    reference_date: date,
) -> tuple[str | None, date | None, date | None]:
    """Extrai produtor e período de uma consulta financeira em linguagem natural."""
    current = _HISTORY_BLOCK_RE.sub("", question).strip()
    producer = _extract_producer_from_text(current)

    period_start: date | None = None
    period_end: date | None = None

    iso_range = _ISO_RANGE_RE.search(current)
    if iso_range:
        candidate_start = date.fromisoformat(iso_range.group(1))
        candidate_end = date.fromisoformat(iso_range.group(2))
        if candidate_end >= candidate_start:
            period_start, period_end = candidate_start, candidate_end
    else:
        br_range = _BR_RANGE_RE.search(current)
        if br_range:
            candidate_start = _parse_br_date(br_range.group(1))
            candidate_end = _parse_br_date(br_range.group(2))
            if candidate_end >= candidate_start:
                period_start, period_end = candidate_start, candidate_end
        else:
            month_match = _MONTH_NAME_RE.search(current)
            if month_match:
                month_key = _normalize_text(month_match.group(1))
                month = _MONTH_NAMES[month_key]
                year = (
                    int(month_match.group(2))
                    if month_match.group(2)
                    else reference_date.year
                )
                last_day = calendar.monthrange(year, month)[1]
                period_start = date(year, month, 1)
                period_end = date(year, month, last_day)
            else:
                iso_month = _ISO_MONTH_RE.search(current)
                if iso_month:
                    year, month = int(iso_month.group(1)), int(iso_month.group(2))
                    if 1 <= month <= 12:
                        last_day = calendar.monthrange(year, month)[1]
                        period_start = date(year, month, 1)
                        period_end = date(year, month, last_day)
                else:
                    br_month = _BR_MONTH_RE.search(current)
                    if br_month:
                        month, year = int(br_month.group(1)), int(br_month.group(2))
                        if 1 <= month <= 12:
                            last_day = calendar.monthrange(year, month)[1]
                            period_start = date(year, month, 1)
                            period_end = date(year, month, last_day)

    return producer, period_start, period_end


def _build_bucket(rows: list[_ParsedFinancialRow]) -> FinancialCalculationBucket:
    if not rows:
        return FinancialCalculationBucket()

    total = sum((r.amount for r in rows), Decimal("0.00"))
    tx_ids: list[str] = []
    src_ids: list[str] = []
    due_dates: list[str] = []
    pay_dates: list[str] = []

    for r in rows:
        if r.transaction_id not in tx_ids:
            tx_ids.append(r.transaction_id)
        if r.source_id not in src_ids:
            src_ids.append(r.source_id)
        if r.due_date is not None:
            iso_due = r.due_date.isoformat()
            if iso_due not in due_dates:
                due_dates.append(iso_due)
        if r.payment_date is not None:
            iso_pay = r.payment_date.isoformat()
            if iso_pay not in pay_dates:
                pay_dates.append(iso_pay)

    return FinancialCalculationBucket(
        total_amount=total,
        formatted_total=format_brl_currency(total),
        transaction_ids=tx_ids,
        source_ids=src_ids,
        due_dates=due_dates,
        payment_dates=pay_dates,
        source_document=rows[0].document_name,
        has_records=True,
    )


def _match_single_producer_rows(
    target: str,
    venda_rows: list[_ParsedFinancialRow],
) -> tuple[list[_ParsedFinancialRow], list[ProducerMatchCandidate]]:
    """Seleciona registros de um único produtor ou retorna candidatos em caso de ambiguidade."""
    is_code_target = bool(re.fullmatch(r"P\d+", target, re.IGNORECASE))
    if is_code_target:
        matched = [r for r in venda_rows if r.producer_id.upper() == target.upper()]
        return matched, []

    producers_by_id: dict[str, str | None] = {}
    for row in venda_rows:
        if row.producer_id not in producers_by_id or (
            producers_by_id[row.producer_id] is None and row.producer_name
        ):
            producers_by_id[row.producer_id] = row.producer_name

    normalized_target = _normalize_text(target)
    exact_ids = [
        pid
        for pid, pname in producers_by_id.items()
        if pname and _normalize_text(pname) == normalized_target
    ]

    if exact_ids:
        matched_ids = sorted(exact_ids)
    else:
        query_tokens = _tokenize_name(target)
        if not query_tokens:
            return [], []
        query_token_set = set(query_tokens)
        matched_ids = sorted(
            pid
            for pid, pname in producers_by_id.items()
            if pname and query_token_set.issubset(set(_tokenize_name(pname)))
        )

    if len(matched_ids) > 1:
        candidates = [
            ProducerMatchCandidate(
                producer_id=pid,
                producer_name=producers_by_id[pid],
            )
            for pid in matched_ids
        ]
        return [], candidates

    if len(matched_ids) == 1:
        resolved_id = matched_ids[0]
        return [r for r in venda_rows if r.producer_id == resolved_id], []

    return [], []


def calculate_producer_financial_summary(
    producer: str,
    *,
    reference_date: date | datetime | str,
    financial_records_provider: FinancialRecordsProvider | None = None,
    financial_records: Sequence[ConsultationSourceItem | Any] | None = None,
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    period: str | None = None,
) -> FinancialSummaryCalculation:
    """Calcula vendas, pagamentos registrados e pendências de um único produtor conforme RF08.

    Exige explicitamente uma fonte exaustiva (`financial_records_provider` ou `financial_records`)
    de `financeiro.csv`, independente de busca semântica limitada por relevância.
    """
    target = producer.strip()
    if not target:
        raise ValueError("producer must not be blank.")

    exhaustive_records = resolve_exhaustive_financial_records(
        financial_records_provider=financial_records_provider,
        financial_records=financial_records,
    )
    if exhaustive_records is None:
        raise ValueError(
            "An exhaustive financial_records_provider or financial_records collection "
            "is required to calculate financial summaries without partial omission."
        )

    ref_date = to_pernambuco_date(reference_date)
    start_date, end_date = resolve_period_bounds(
        period,
        period_start=period_start,
        period_end=period_end,
        fallback_reference_date=ref_date,
    )

    venda_rows: list[_ParsedFinancialRow] = []
    seen_tx_keys: set[tuple[str, str]] = set()
    for src in exhaustive_records:
        parsed = _extract_financial_row(src)
        if parsed is None or parsed.transaction_type != "venda":
            continue
        tx_key = (parsed.transaction_id, parsed.producer_id.upper())
        if tx_key in seen_tx_keys:
            continue
        seen_tx_keys.add(tx_key)
        venda_rows.append(parsed)

    producer_rows, ambiguous_candidates = _match_single_producer_rows(
        target,
        venda_rows,
    )

    if ambiguous_candidates:
        candidates_desc = ", ".join(
            f"{c.producer_id} ({c.producer_name})" if c.producer_name else c.producer_id
            for c in ambiguous_candidates
        )
        clarification = (
            f"Foram encontrados múltiplos produtores correspondentes a '{target}' em "
            f"{FINANCIAL_SOURCE_FILENAME}: {candidates_desc}. "
            "Informe o código do produtor ou o nome completo para calcular o resumo "
            "financeiro de um único produtor."
        )
        return FinancialSummaryCalculation(
            producer_id=target,
            producer_name=None,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            reference_date=ref_date.isoformat(),
            source_document=FINANCIAL_SOURCE_FILENAME,
            has_any_records=False,
            is_ambiguous_producer=True,
            matching_producers=ambiguous_candidates,
            clarification_message=clarification,
            is_exhaustive_source=True,
        )

    sales_rows = [
        r
        for r in producer_rows
        if start_date <= r.transaction_date <= end_date
        and r.transaction_date <= ref_date
    ]
    payment_rows = [
        r
        for r in producer_rows
        if r.payment_date is not None
        and start_date <= r.payment_date <= end_date
        and r.payment_date <= ref_date
    ]
    pending_rows = [
        r
        for r in producer_rows
        if r.transaction_date <= ref_date
        and (r.payment_date is None or r.payment_date > ref_date)
    ]
    overdue_rows = [
        r
        for r in pending_rows
        if r.due_date is not None and r.due_date < ref_date
    ]
    upcoming_rows = [
        r
        for r in pending_rows
        if r.due_date is None or r.due_date >= ref_date
    ]

    sales_bucket = _build_bucket(sales_rows)
    payments_bucket = _build_bucket(payment_rows)
    pending_total_bucket = _build_bucket(pending_rows)
    overdue_bucket = _build_bucket(overdue_rows)
    upcoming_bucket = _build_bucket(upcoming_rows)

    all_tx_ids: list[str] = []
    all_src_ids: list[str] = []
    for bucket in (sales_bucket, payments_bucket, pending_total_bucket):
        for tx_id in bucket.transaction_ids:
            if tx_id not in all_tx_ids:
                all_tx_ids.append(tx_id)
        for src_id in bucket.source_ids:
            if src_id not in all_src_ids:
                all_src_ids.append(src_id)

    resolved_producer_id = producer_rows[0].producer_id if producer_rows else target
    resolved_producer_name = next(
        (r.producer_name for r in producer_rows if r.producer_name),
        None,
    )
    doc_name = producer_rows[0].document_name if producer_rows else FINANCIAL_SOURCE_FILENAME

    return FinancialSummaryCalculation(
        producer_id=resolved_producer_id,
        producer_name=resolved_producer_name,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        reference_date=ref_date.isoformat(),
        source_document=doc_name,
        sales_in_period=sales_bucket,
        registered_payments_in_period=payments_bucket,
        pending_total=pending_total_bucket,
        pending_overdue=overdue_bucket,
        pending_upcoming=upcoming_bucket,
        all_transaction_ids=all_tx_ids,
        all_source_ids=all_src_ids,
        has_any_records=bool(all_tx_ids),
        is_ambiguous_producer=False,
        matching_producers=[],
        clarification_message=None,
        is_exhaustive_source=True,
    )


def build_financial_summary_tool(
    financial_records_provider: FinancialRecordsProvider | None = None,
    *,
    financial_records: Sequence[ConsultationSourceItem | Any] | None = None,
    on_calculation: Callable[[FinancialSummaryCalculation], None] | None = None,
) -> Callable[[str, str, str, str], dict[str, Any]]:
    """Cria a ferramenta ADK de cálculo financeiro vinculada à fonte exaustiva de financeiro.csv."""

    def calcular_resumo_financeiro_produtor(
        producer: str,
        period_start: str,
        period_end: str,
        reference_date: str,
    ) -> dict[str, Any]:
        """Calcula vendas, pagamentos registrados e pendências financeiras de um produtor em financeiro.csv."""
        resolved = resolve_exhaustive_financial_records(
            financial_records_provider=financial_records_provider,
            financial_records=financial_records,
        )
        if resolved is None:
            return {
                "error": (
                    "A coleção exaustiva de registros de financeiro.csv não foi "
                    "fornecida; não é possível garantir cálculos completos."
                ),
                "is_exhaustive_source": False,
            }
        result = calculate_producer_financial_summary(
            producer=producer,
            period_start=period_start,
            period_end=period_end,
            reference_date=reference_date,
            financial_records=resolved,
        )
        if on_calculation is not None:
            on_calculation(result)
        return result.model_dump(mode="json")

    return calcular_resumo_financeiro_produtor
