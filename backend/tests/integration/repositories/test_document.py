from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.document import Document
from api.repositories.document import DocumentRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_create_preserves_document_fields(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)

    document = await repository.create("Certificado.pdf", "key-1")

    assert isinstance(document.id, UUID)
    assert document.original_filename == "Certificado.pdf"
    assert document.storage_key == "key-1"


async def test_list_all_returns_empty_list(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)

    assert await repository.list_all() == []


async def test_list_all_orders_by_filename_then_id(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)
    first_id = UUID(int=1)
    second_id = UUID(int=2)
    last_id = UUID(int=3)
    db_session.add_all([
        Document(id=last_id, original_filename="b.pdf", storage_key="key-3"),
        Document(id=second_id, original_filename="a.pdf", storage_key="key-2"),
        Document(id=first_id, original_filename="a.pdf", storage_key="key-1"),
    ])
    await db_session.flush()

    documents = await repository.list_all()

    assert [document.id for document in documents] == [first_id, second_id, last_id]


async def test_get_by_id_finds_document(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)
    document = await repository.create("certificado.pdf", "key-1")
    document_id = document.id
    db_session.expunge(document)

    result = await repository.get_by_id(document_id)

    assert result is not None
    assert result.id == document_id


async def test_get_by_id_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)

    assert await repository.get_by_id(uuid4()) is None


async def test_delete_removes_only_selected_document(db_session: AsyncSession) -> None:
    repository = DocumentRepository(db_session)
    document = await repository.create("certificado.pdf", "key-1")
    other = await repository.create("certificado.pdf", "key-2")
    document_id = document.id
    other_id = other.id
    db_session.expunge(other)

    await repository.delete(document)

    assert await repository.get_by_id(document_id) is None
    assert await repository.get_by_id(other_id) is not None
