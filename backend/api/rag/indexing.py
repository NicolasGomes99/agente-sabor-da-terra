import hashlib
import logging
from asyncio import to_thread
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from ..models.document import Document, DocumentChunk, DocumentProcessingStatus
from ..repositories.document import DocumentRepository
from ..storage.base import DocumentStorage
from .embeddings import EmbeddingClient
from .extractors import (
    ExtractedChunk,
    extract_document_chunks,
    is_indexable_document,
)

logger = logging.getLogger(__name__)

FACEPE_DOCUMENT_SUBDIRS: tuple[str, ...] = (
    "certificacoes",
    "contratos",
    "fichas_tecnicas",
)

FACEPE_CSV_FILES: tuple[str, ...] = (
    "financeiro.csv",
    "lotes.csv",
    "produtores.csv",
    "sazonalidade.csv",
    "tabela_precos_outubro_2026.csv",
)


class DocumentIndexingNotFoundError(LookupError):
    """Documento não encontrado para processamento/indexação."""


class UnsupportedDocumentFormatError(ValueError):
    """Formato de documento não suportado para extração/indexação textual ou CSV."""


@dataclass(frozen=True)
class DocumentIndexingSummary:
    document_id: UUID
    original_filename: str
    status: str
    chunks_created: int = 0
    chunks_updated: int = 0
    chunks_preserved_cited: int = 0
    chunks_deleted: int = 0
    active_chunk_count: int = 0
    error: str | None = None


@dataclass
class FacepeDocumentLoadSummary:
    documents_created: int = 0
    documents_reused: int = 0
    documents_indexed: int = 0
    documents_skipped: int = 0
    documents_failed: int = 0
    total_active_chunks: int = 0
    chunks_by_filename: dict[str, int] = field(default_factory=dict)


def discover_facepe_documents(data_dir: Path) -> list[tuple[str, Path]]:
    """Lista de forma determinística os 20 TXTs e 5 CSVs oficiais da base Facepe."""
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Diretório da base Facepe não encontrado: {data_dir}")

    discovered: list[tuple[str, Path]] = []

    for subdir_name in FACEPE_DOCUMENT_SUBDIRS:
        subdir = data_dir / subdir_name
        if not subdir.is_dir():
            raise FileNotFoundError(
                f"Subdiretório obrigatório da base Facepe não encontrado: {subdir}"
            )
        txt_files = sorted(
            path
            for path in subdir.iterdir()
            if path.is_file() and path.suffix.lower() == ".txt"
        )
        for path in txt_files:
            rel_path = f"{subdir_name}/{path.name}"
            discovered.append((rel_path, path))

    for csv_name in FACEPE_CSV_FILES:
        csv_path = data_dir / csv_name
        if not csv_path.is_file():
            raise FileNotFoundError(
                f"Arquivo CSV obrigatório da base Facepe não encontrado: {csv_path}"
            )
        discovered.append((csv_name, csv_path))

    return discovered


def _read_storage_bytes(storage: DocumentStorage, storage_key: str) -> bytes:
    with storage.open(storage_key) as reader:
        return reader.read()


def _sha256_hex(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _match_existing_chunk(
    extracted: ExtractedChunk,
    *,
    by_chunk_key: dict[str, DocumentChunk],
    by_record_id: dict[str, DocumentChunk],
    by_content: dict[str, list[DocumentChunk]],
    used_ids: set[UUID],
) -> DocumentChunk | None:
    candidate = by_chunk_key.get(extracted.chunk_key)
    if candidate is not None and candidate.id not in used_ids:
        return candidate

    if extracted.record_id:
        rec_candidate = by_record_id.get(extracted.record_id)
        if rec_candidate is not None and rec_candidate.id not in used_ids:
            return rec_candidate

    for content_candidate in by_content.get(extracted.content, ()):
        if content_candidate.id not in used_ids:
            return content_candidate

    return None


class DocumentIndexingService:
    """Processa, gera embeddings e indexa documentos TXT e CSV com pgvector."""

    def __init__(
        self,
        repository: DocumentRepository,
        storage: DocumentStorage,
        embedding_client: EmbeddingClient,
        *,
        max_text_chars: int = 1600,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.embedding_client = embedding_client
        self.max_text_chars = max_text_chars
        self.session = repository.session

    async def index_document(
        self,
        document_id: UUID,
        *,
        raise_on_error: bool = True,
    ) -> DocumentIndexingSummary:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            raise DocumentIndexingNotFoundError(document_id)

        if not is_indexable_document(document.original_filename):
            raise UnsupportedDocumentFormatError(
                f"O documento '{document.original_filename}' não possui formato suportado "
                "para indexação (suportados: TXT e CSV)."
            )

        # Etapa 1 (fora da transação de gravação de chunks): leitura, extração e embeddings.
        # Se qualquer etapa falhar, nenhum trecho parcial é gravado na base consultável.
        try:
            raw_bytes = await to_thread(
                _read_storage_bytes,
                self.storage,
                document.storage_key,
            )
            content_hash = _sha256_hex(raw_bytes)
            extracted_chunks = extract_document_chunks(
                raw_bytes,
                filename=document.original_filename,
                max_text_chars=self.max_text_chars,
            )
            vectors = await self.embedding_client.embed_documents(
                [chunk.content for chunk in extracted_chunks]
            )
            if len(vectors) != len(extracted_chunks):
                raise RuntimeError(
                    "Quantidade de embeddings divergente da quantidade de trechos extraídos."
                )
        except Exception as error:
            error_message = str(error).strip()[:1000] or type(error).__name__
            await self._record_failure(document_id, error_message)
            if raise_on_error:
                raise
            return DocumentIndexingSummary(
                document_id=document_id,
                original_filename=document.original_filename,
                status=DocumentProcessingStatus.FAILED.value,
                error=error_message,
            )

        # Etapa 2 (transação atômica): atualiza trechos preservando citações existentes.
        try:
            summary = await self._persist_indexed_chunks(
                document_id=document_id,
                content_hash=content_hash,
                extracted_chunks=extracted_chunks,
                vectors=vectors,
            )
            await self.session.commit()
            return summary
        except Exception as error:
            await self.session.rollback()
            error_message = str(error).strip()[:1000] or type(error).__name__
            await self._record_failure(document_id, error_message)
            if raise_on_error:
                raise
            return DocumentIndexingSummary(
                document_id=document_id,
                original_filename=document.original_filename,
                status=DocumentProcessingStatus.FAILED.value,
                error=error_message,
            )

    async def _persist_indexed_chunks(
        self,
        *,
        document_id: UUID,
        content_hash: str,
        extracted_chunks: list[ExtractedChunk],
        vectors: list[list[float]],
    ) -> DocumentIndexingSummary:
        document = await self.repository.get_by_id(document_id)

        if document is None:
            raise DocumentIndexingNotFoundError(document_id)

        existing_chunks = await self.repository.list_chunks_by_document(
            document_id
        )

        cited_chunk_ids = (
            await self.repository.list_cited_chunk_ids_by_document(
                document_id
            )
        )

        by_chunk_key: dict[str, DocumentChunk] = {}
        by_record_id: dict[str, DocumentChunk] = {}
        by_content: dict[str, list[DocumentChunk]] = {}

        for existing in existing_chunks:
            # Versões históricas não devem ser reutilizadas ou sobrescritas.
            if not existing.is_active:
                continue

            if (
                existing.chunk_key
                and existing.chunk_key not in by_chunk_key
            ):
                by_chunk_key[existing.chunk_key] = existing

            if (
                existing.record_id
                and existing.record_id not in by_record_id
            ):
                by_record_id[existing.record_id] = existing

            by_content.setdefault(existing.content, []).append(existing)

        used_ids: set[UUID] = set()
        chunks_created = 0
        chunks_updated = 0
        chunks_preserved_cited = 0
        chunks_deleted = 0

        for extracted, vector in zip(
            extracted_chunks,
            vectors,
            strict=True,
        ):
            record_fields = (
                dict(extracted.record_fields)
                if extracted.record_fields is not None
                else None
            )

            matched = _match_existing_chunk(
                extracted,
                by_chunk_key=by_chunk_key,
                by_record_id=by_record_id,
                by_content=by_content,
                used_ids=used_ids,
            )

            def has_same_evidence(
                candidate: DocumentChunk,
                extracted_chunk: ExtractedChunk = extracted,
                fields: dict[str, str] | None = record_fields,
            ) -> bool:
                return (
                    candidate.content == extracted_chunk.content
                    and candidate.record_id == extracted_chunk.record_id
                    and candidate.record_fields == fields
                )

            # Prioriza a reutilização de evidências inalteradas,
            # inclusive quando sua posição no documento muda.
            if matched is None or not has_same_evidence(matched):
                unchanged = next(
                    (
                        candidate
                        for candidate in by_content.get(
                            extracted.content, ()
                        )
                        if candidate.id not in used_ids
                        and has_same_evidence(candidate)
                    ),
                    None,
                )

                if unchanged is not None:
                    matched = unchanged

            # Trechos citados não podem ter sua evidência modificada.
            # A versão original será preservada na etapa de limpeza.
            if (
                matched is not None
                and matched.id in cited_chunk_ids
                and not has_same_evidence(matched)
            ):
                matched = None

            if matched is not None:
                used_ids.add(matched.id)

                matched.content = extracted.content
                matched.embedding = list(vector)
                matched.embedding_model = self.embedding_client.model_name
                matched.chunk_index = extracted.chunk_index
                matched.chunk_key = extracted.chunk_key
                matched.record_id = extracted.record_id
                matched.record_fields = record_fields
                matched.is_active = True

                chunks_updated += 1

            else:
                new_chunk = DocumentChunk(
                    document_id=document.id,
                    content=extracted.content,
                    embedding=list(vector),
                    embedding_model=self.embedding_client.model_name,
                    chunk_index=extracted.chunk_index,
                    chunk_key=extracted.chunk_key,
                    is_active=True,
                    record_id=extracted.record_id,
                    record_fields=record_fields,
                )

                self.session.add(new_chunk)
                chunks_created += 1

        for existing in existing_chunks:
            if existing.id in used_ids:
                continue

            if existing.id in cited_chunk_ids:
                # Preserva a evidência original e a integridade da citação,
                # mas impede a recuperação de conteúdo obsoleto.
                existing.is_active = False
                chunks_preserved_cited += 1

            else:
                await self.session.delete(existing)
                chunks_deleted += 1

        document.content_sha256 = content_hash
        document.processing_status = DocumentProcessingStatus.INDEXED.value
        document.processing_error = None
        document.indexed_at = datetime.now(UTC)

        await self.session.flush()

        return DocumentIndexingSummary(
            document_id=document.id,
            original_filename=document.original_filename,
            status=document.processing_status,
            chunks_created=chunks_created,
            chunks_updated=chunks_updated,
            chunks_preserved_cited=chunks_preserved_cited,
            chunks_deleted=chunks_deleted,
            active_chunk_count=len(extracted_chunks),
        )

    async def _record_failure(self, document_id: UUID, error_message: str) -> None:
        try:
            document = await self.repository.get_by_id(document_id)
            if document is None:
                return
            document.processing_status = DocumentProcessingStatus.FAILED.value
            document.processing_error = error_message
            await self.session.commit()
        except Exception:
            logger.exception(
                "Falha ao registrar erro de processamento do documento %s",
                document_id,
            )
            await self.session.rollback()

    async def list_documents_by_status(
        self,
        statuses: tuple[str, ...] | None = None,
    ) -> list[tuple[Document, int]]:
        documents = await self.repository.list_by_processing_status(statuses)
        counts = await self.repository.count_active_chunks_by_documents(
            [doc.id for doc in documents]
        )
        return [(doc, counts.get(doc.id, 0)) for doc in documents]

    async def list_pending_or_failed(self) -> list[Document]:
        return await self.repository.list_by_processing_status(
            (
                DocumentProcessingStatus.PENDING.value,
                DocumentProcessingStatus.FAILED.value,
            )
        )

    async def retry_pending_and_failed(self) -> list[DocumentIndexingSummary]:
        candidates = await self.list_pending_or_failed()
        summaries: list[DocumentIndexingSummary] = []
        for document in candidates:
            if not is_indexable_document(document.original_filename):
                continue
            summaries.append(
                await self.index_document(document.id, raise_on_error=False)
            )
        return summaries

    async def load_facepe_documents(
        self,
        data_dir: Path,
        *,
        reindex_existing: bool = False,
    ) -> FacepeDocumentLoadSummary:
        """Armazena, processa e indexa os documentos da base Facepe."""
        files = discover_facepe_documents(data_dir)
        summary = FacepeDocumentLoadSummary()

        for source_path, file_path in files:
            raw_bytes = await to_thread(file_path.read_bytes)
            content_hash = _sha256_hex(raw_bytes)

            existing = await self.repository.get_by_source_path(
                source_path
            )

            if existing is None:
                storage_key = uuid4().hex

                await to_thread(
                    self.storage.save,
                    storage_key,
                    BytesIO(raw_bytes),
                )

                try:
                    document = await self.repository.create(
                        file_path.name,
                        storage_key,
                        source_path=source_path,
                        content_sha256=content_hash,
                        processing_status=(
                            DocumentProcessingStatus.PENDING.value
                        ),
                    )

                except Exception:
                    await self.session.rollback()

                    try:
                        await to_thread(
                            self.storage.delete,
                            storage_key,
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao remover arquivo órfão %s",
                            storage_key,
                        )

                    raise

                await self.session.commit()

                summary.documents_created += 1

            else:
                document = existing
                summary.documents_reused += 1

                content_changed = (
                    document.content_sha256 != content_hash
                )

                is_unchanged_indexed = (
                    document.processing_status
                    == DocumentProcessingStatus.INDEXED.value
                    and not content_changed
                    and not reindex_existing
                )

                if is_unchanged_indexed:
                    counts = (
                        await self.repository.count_active_chunks_by_documents(
                            [document.id]
                        )
                    )

                    active_count = counts.get(document.id, 0)

                    summary.documents_skipped += 1
                    summary.total_active_chunks += active_count
                    summary.chunks_by_filename[
                        document.original_filename
                    ] = active_count

                    continue

                if content_changed:
                    previous_storage_key = document.storage_key
                    new_storage_key = uuid4().hex

                    # Os adaptadores de armazenamento não permitem
                    # sobrescrever arquivos existentes.
                    await to_thread(
                        self.storage.save,
                        new_storage_key,
                        BytesIO(raw_bytes),
                    )

                    try:
                        document.storage_key = new_storage_key
                        document.content_sha256 = content_hash
                        document.processing_status = (
                            DocumentProcessingStatus.PENDING.value
                        )
                        document.processing_error = None
                        document.indexed_at = None

                        await self.session.flush()

                    except Exception:
                        await self.session.rollback()

                        try:
                            await to_thread(
                                self.storage.delete,
                                new_storage_key,
                            )

                        except Exception:
                            logger.exception(
                                "Falha ao remover arquivo órfão %s",
                                new_storage_key,
                            )

                        raise

                    # O conteúdo anterior permanece no armazenamento.
                    # O documento mantém sua identidade no banco.
                    await self.session.commit()

                    logger.info(
                        "Documento %s atualizado: storage_key %s -> %s",
                        document.id,
                        previous_storage_key,
                        new_storage_key,
                    )

            try:
                result = await self.index_document(
                    document.id,
                    raise_on_error=True,
                )

            except Exception:
                summary.documents_failed += 1
                raise

            summary.documents_indexed += 1
            summary.total_active_chunks += result.active_chunk_count

            summary.chunks_by_filename[
                document.original_filename
            ] = result.active_chunk_count

        return summary