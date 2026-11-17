from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, original_filename: str, storage_key: str) -> Document:
        document = Document(original_filename=original_filename, storage_key=storage_key)
        self.session.add(document)
        await self.session.flush()
        return document

    async def list_all(self) -> list[Document]:
        statement = select(Document).order_by(Document.original_filename, Document.id)
        result = await self.session.scalars(statement)
        return list(result)

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.flush()
