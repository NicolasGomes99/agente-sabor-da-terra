from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession
from ..models.citation import Citation
from ..models.document import Document, DocumentChunk, DocumentProcessingStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        original_filename: str,
        storage_key: str,
        *,
        source_path: str | None = None,
        content_sha256: str | None = None,
        processing_status: str = DocumentProcessingStatus.PENDING.value,
    ) -> Document:
        document = Document(
            original_filename=original_filename,
            storage_key=storage_key,
            source_path=source_path,
            content_sha256=content_sha256,
            processing_status=processing_status,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def list_all(self) -> list[Document]:
        statement = select(Document).order_by(Document.original_filename, Document.id)
        result = await self.session.scalars(statement)
        return list(result)

    async def list_by_processing_status(
        self,
        statuses: Sequence[str] | None = None,
    ) -> list[Document]:
        statement = select(Document)
        if statuses:
            statement = statement.where(Document.processing_status.in_(list(statuses)))
        statement = statement.order_by(Document.original_filename, Document.id)
        result = await self.session.scalars(statement)
        return list(result)

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def list_chunks(self, *, limit: int = 50) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .options(selectinload(DocumentChunk.document))
            .order_by(
                Document.original_filename.asc(),
                DocumentChunk.record_id.asc().nullslast(),
                DocumentChunk.id.asc(),
            )
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_by_source_path(self, source_path: str) -> Document | None:
        statement = select(Document).where(Document.source_path == source_path)
        return await self.session.scalar(statement)

    async def list_chunks_by_ids(
        self, chunk_ids: Sequence[UUID]
    ) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.id.in_(list(chunk_ids)))
            .options(selectinload(DocumentChunk.document))
        )
        chunks_by_id = {
            chunk.id: chunk for chunk in (await self.session.scalars(statement)).all()
        }
        ordered: list[DocumentChunk] = []
        seen: set[UUID] = set()
        for cid in chunk_ids:
            if cid in chunks_by_id and cid not in seen:
                seen.add(cid)
                ordered.append(chunks_by_id[cid])
        return ordered

    async def list_chunks_by_document(
        self,
        document_id: UUID,
        *,
        only_active: bool = False,
    ) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .options(selectinload(DocumentChunk.document))
            .order_by(DocumentChunk.chunk_index.asc(), DocumentChunk.id.asc())
        )
        if only_active:
            statement = statement.where(DocumentChunk.is_active.is_(True))
        result = await self.session.scalars(statement)
        return list(result)

    async def list_cited_chunk_ids_by_document(self, document_id: UUID) -> set[UUID]:
        statement = (
            select(Citation.chunk_id)
            .join(DocumentChunk, Citation.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.document_id == document_id)
            .distinct()
        )
        result = await self.session.scalars(statement)
        return set(result.all())

    async def count_active_chunks_by_documents(
        self,
        document_ids: Sequence[UUID],
    ) -> dict[UUID, int]:
        if not document_ids:
            return {}
        statement = (
            select(DocumentChunk.document_id, func.count(DocumentChunk.id))
            .where(
                DocumentChunk.document_id.in_(list(document_ids)),
                DocumentChunk.is_active.is_(True),
            )
            .group_by(DocumentChunk.document_id)
        )
        rows = (await self.session.execute(statement)).all()
        return {doc_id: int(count) for doc_id, count in rows}

    async def semantic_search_chunks(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[UUID] | None = None,
        document_names: Sequence[str] | None = None,
    ) -> list[DocumentChunk]:
        if top_k < 1 or not query_embedding:
            return []
        vector_values = [float(v) for v in query_embedding]
        distance = DocumentChunk.embedding.cosine_distance(vector_values)
        statement = (
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.processing_status == DocumentProcessingStatus.INDEXED.value,
                DocumentChunk.is_active.is_(True),
                DocumentChunk.embedding.is_not(None),
                func.vector_dims(DocumentChunk.embedding) == len(vector_values),
            )
            .options(selectinload(DocumentChunk.document))
            .order_by(distance.asc(), DocumentChunk.chunk_index.asc(), DocumentChunk.id.asc())
            .limit(top_k)
        )
        if document_ids:
            statement = statement.where(Document.id.in_(list(document_ids)))
        if document_names:
            normalized_names = [name.strip().lower() for name in document_names if name.strip()]
            if normalized_names:
                statement = statement.where(
                    func.lower(Document.original_filename).in_(normalized_names)
                )
        result = await self.session.scalars(statement)
        return list(result)

    async def list_indexed_chunks(
        self,
        *,
        document_name: str | None = None,
        document_names: Sequence[str] | None = None,
        document_ids: Sequence[UUID] | None = None,
        record_ids: Sequence[str] | None = None,
        only_records: bool = False,
    ) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.processing_status == DocumentProcessingStatus.INDEXED.value,
                DocumentChunk.is_active.is_(True),
            )
            .options(selectinload(DocumentChunk.document))
            .order_by(
                Document.original_filename.asc(),
                DocumentChunk.chunk_index.asc(),
                DocumentChunk.id.asc(),
            )
        )
        if document_name is not None and document_name.strip():
            statement = statement.where(
                func.lower(Document.original_filename) == document_name.strip().lower()
            )
        if document_names:
            normalized = [name.strip().lower() for name in document_names if name.strip()]
            if normalized:
                statement = statement.where(
                    func.lower(Document.original_filename).in_(normalized)
                )
        if document_ids:
            statement = statement.where(Document.id.in_(list(document_ids)))
        if record_ids:
            normalized_ids = [rid.strip().lower() for rid in record_ids if rid.strip()]
            if normalized_ids:
                statement = statement.where(
                    func.lower(DocumentChunk.record_id).in_(normalized_ids)
                )
        if only_records:
            statement = statement.where(DocumentChunk.record_id.is_not(None))
        result = await self.session.scalars(statement)
        return list(result)

    async def list_citations_by_document(
        self, document_id: UUID
    ) -> list[tuple[Citation, DocumentChunk, ChatMessage, ChatSession]]:
        statement = (
            select(Citation, DocumentChunk, ChatMessage, ChatSession)
            .join(DocumentChunk, Citation.chunk_id == DocumentChunk.id)
            .join(ChatMessage, Citation.message_id == ChatMessage.id)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(DocumentChunk.document_id == document_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await self.session.execute(statement)
        return list(result.all())

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.flush()
