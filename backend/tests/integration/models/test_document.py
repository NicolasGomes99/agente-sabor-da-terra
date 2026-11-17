from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.document import Document

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_document_persists_with_generated_uuid(db_session: AsyncSession) -> None:
    document = Document(original_filename="certificado.pdf", storage_key="key-1")
    db_session.add(document)
    await db_session.flush()

    document_id = document.id
    assert isinstance(document_id, UUID)
    db_session.expunge(document)

    persisted_document = await db_session.get(Document, document_id)

    assert persisted_document is not None
    assert persisted_document.original_filename == "certificado.pdf"
    assert persisted_document.storage_key == "key-1"


async def test_documents_can_share_original_filename(db_session: AsyncSession) -> None:
    first = Document(original_filename="certificado.pdf", storage_key="key-1")
    second = Document(original_filename="certificado.pdf", storage_key="key-2")
    db_session.add_all([first, second])
    await db_session.flush()

    first_id, second_id = first.id, second.id
    assert first_id != second_id
    db_session.expunge(first)
    db_session.expunge(second)

    persisted_first = await db_session.get(Document, first_id)
    persisted_second = await db_session.get(Document, second_id)

    assert persisted_first is not None
    assert persisted_second is not None
    assert persisted_first.original_filename == persisted_second.original_filename == "certificado.pdf"
    assert persisted_first.storage_key == "key-1"
    assert persisted_second.storage_key == "key-2"


async def test_duplicate_storage_key_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(Document(original_filename="certificado.pdf", storage_key="key-1"))
    await db_session.flush()

    db_session.add(Document(original_filename="relatorio.pdf", storage_key="key-1"))

    with pytest.raises(IntegrityError):
        await db_session.flush()
