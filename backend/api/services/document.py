import logging
from asyncio import CancelledError, create_task, shield, to_thread, wait
from collections.abc import Callable, Coroutine
from functools import partial
from typing import BinaryIO
from uuid import UUID, uuid4

from anyio import CancelScope

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession
from ..models.citation import Citation
from ..models.document import Document, DocumentChunk
from ..repositories.document import DocumentRepository
from ..storage.base import DocumentReader, DocumentStorage

logger = logging.getLogger(__name__)


async def _finish_write[T](operation: Coroutine[object, object, T]) -> T:
    task = create_task(operation)
    try:
        return await shield(task)
    except CancelledError:
        with CancelScope(shield=True):
            while not task.done():
                try:
                    await wait((task,))
                except CancelledError:
                    continue
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error("Document operation failed after request cancellation", exc_info=error)
        raise


class DocumentNotFoundError(LookupError):
    pass


class DocumentCitedError(Exception):
    def __init__(
        self,
        document: Document,
        citations: list[tuple[Citation, DocumentChunk, ChatMessage, ChatSession]],
    ) -> None:
        self.document = document
        self.citations = citations
        first_citation, first_chunk, first_message, first_session = citations[0]
        excerpt = (
            f"{first_chunk.content[:80]}..."
            if len(first_chunk.content) > 80
            else first_chunk.content
        )
        super().__init__(
            f"Não é possível excluir o documento '{document.original_filename}' porque ele é citado "
            f"na conversa '{first_session.title}' (citação message_id={first_citation.message_id}, "
            f"chunk_id={first_citation.chunk_id}, trecho: \"{excerpt}\")."
        )


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
        return await _finish_write(self._create_document(original_filename, source))

    async def _create_document(self, original_filename: str, source: BinaryIO) -> Document:
        key = uuid4().hex
        await to_thread(self.storage.save, key, source)

        try:
            document = await self.repository.create(original_filename, key)
        except Exception:
            await self._rollback()
            try:
                await to_thread(self.storage.delete, key)
            except Exception:
                logger.exception("Failed to clean up document file %s", key)
            raise

        try:
            await self.repository.session.commit()
        except Exception:
            logger.exception("Could not confirm document creation for storage key %s", key)
            await self._rollback()
            raise

        return document

    async def prepare_document_read(
        self, document_id: UUID
    ) -> tuple[str, Callable[[], DocumentReader]]:
        document = await self._get_document(document_id)
        return document.original_filename, partial(self.storage.open, document.storage_key)

    async def delete_document(self, document_id: UUID) -> None:
        await _finish_write(self._delete_document(document_id))

    async def _delete_document(self, document_id: UUID) -> None:
        document = await self._get_document(document_id)

        citations = await self.repository.list_citations_by_document(document.id)
        if citations:
            raise DocumentCitedError(document, citations)

        key = document.storage_key

        try:
            await self.repository.delete(document)
        except Exception:
            await self._rollback()
            raise

        try:
            await self.repository.session.commit()
        except Exception:
            logger.exception("Could not confirm deletion of document %s (key %s)", document_id, key)
            await self._rollback()
            raise

        try:
            await to_thread(self.storage.delete, key)
        except Exception:
            logger.exception("Failed to remove file for deleted document %s (key %s)", document_id, key)
            raise

    async def _rollback(self) -> None:
        try:
            await self.repository.session.rollback()
        except Exception:
            logger.exception("Failed to roll back document transaction")

    async def _get_document(self, document_id: UUID) -> Document:
        document = await self.repository.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document