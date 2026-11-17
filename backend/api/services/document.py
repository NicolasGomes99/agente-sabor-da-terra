import logging
from asyncio import to_thread
from typing import BinaryIO
from uuid import UUID, uuid4

from ..models.document import Document
from ..repositories.document import DocumentRepository
from ..storage.base import DocumentReader, DocumentStorage

logger = logging.getLogger(__name__)


class DocumentNotFoundError(LookupError):
    pass


class DocumentService:
    def __init__(
        self, repository: DocumentRepository, storage: DocumentStorage
    ) -> None:
        self.repository = repository
        self.storage = storage

    async def list_documents(self) -> list[Document]:
        return await self.repository.list_all()

    async def create_document(
        self, original_filename: str, source: BinaryIO
    ) -> Document:
        key = uuid4().hex
        await to_thread(self.storage.save, key, source)

        try:
            document = await self.repository.create(original_filename, key)
            await self.repository.session.commit()
        except Exception:
            try:
                await self.repository.session.rollback()
            finally:
                try:
                    await to_thread(self.storage.delete, key)
                except Exception:
                    logger.exception("Failed to clean up document file %s", key)
            raise

        return document

    async def open_document(self, document_id: UUID) -> tuple[str, DocumentReader]:
        document = await self._get_document(document_id)
        reader = await to_thread(self.storage.open, document.storage_key)
        return document.original_filename, reader

    async def delete_document(self, document_id: UUID) -> None:
        document = await self._get_document(document_id)
        key = document.storage_key

        try:
            await self.repository.delete(document)
            await to_thread(self.storage.delete, key)
            await self.repository.session.commit()
        except Exception:
            await self.repository.session.rollback()
            raise

    async def _get_document(self, document_id: UUID) -> Document:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document
