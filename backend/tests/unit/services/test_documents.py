from io import BytesIO
from unittest.mock import Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.document import Document
from api.repositories.document import DocumentRepository
from api.services.document import DocumentNotFoundError, DocumentService
from api.storage.base import DocumentStorage


@pytest.fixture
def document() -> Document:
    return Document(id=uuid4(), original_filename="certificado.pdf", storage_key="key")


@pytest.fixture
def operations() -> Mock:
    operations = Mock()
    operations.repository = Mock(spec=DocumentRepository)
    operations.session = Mock(spec=AsyncSession)
    operations.repository.session = operations.session
    operations.storage = Mock(spec=DocumentStorage)
    return operations


@pytest.fixture
def service(operations: Mock) -> DocumentService:
    return DocumentService(operations.repository, operations.storage)


@pytest.mark.asyncio
async def test_list_preserves_repository_order(service, operations, document):
    other = Document(id=uuid4(), original_filename="a.pdf", storage_key="other")
    operations.repository.list_all.return_value = [document, other]

    assert await service.list_documents() == [document, other]
    operations.repository.list_all.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_create_saves_file_before_committing(service, operations, document):
    operations.repository.create.return_value = document

    with BytesIO(b"content") as source:
        result = await service.create_document(document.original_filename, source)

    key = operations.storage.save.call_args.args[0]
    assert key
    assert result is document
    assert operations.mock_calls == [
        call.storage.save(key, source),
        call.repository.create(document.original_filename, key),
        call.session.commit(),
    ]


@pytest.mark.asyncio
async def test_create_stops_when_storage_fails(service, operations, document):
    error = OSError("storage unavailable")
    operations.storage.save.side_effect = error

    with BytesIO(b"content") as source, pytest.raises(OSError) as raised:
        await service.create_document(document.original_filename, source)

    assert raised.value is error
    assert [entry[0] for entry in operations.mock_calls] == ["storage.save"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_create_rolls_back_and_cleans_up_after_insert_failure(
    service, operations, document, cleanup_fails, caplog
):
    error = RuntimeError("insert failed")
    operations.repository.create.side_effect = error
    if cleanup_fails:
        operations.storage.delete.side_effect = OSError("cleanup failed")

    with BytesIO(b"content") as source, pytest.raises(RuntimeError) as raised:
        await service.create_document(document.original_filename, source)

    assert raised.value is error
    key = operations.storage.save.call_args.args[0]
    assert operations.mock_calls == [
        call.storage.save(key, source),
        call.repository.create(document.original_filename, key),
        call.session.rollback(),
        call.storage.delete(key),
    ]
    if cleanup_fails:
        assert "Failed to clean up document file" in caplog.text


@pytest.mark.asyncio
async def test_open_returns_original_filename_and_reader(service, operations, document):
    operations.repository.get_by_id.return_value = document

    with BytesIO(b"content") as reader:
        operations.storage.open.return_value = reader
        result = await service.open_document(document.id)
        assert result == (document.original_filename, reader)
        assert not reader.closed

    assert operations.mock_calls == [
        call.repository.get_by_id(document.id),
        call.storage.open(document.storage_key),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["open_document", "delete_document"])
async def test_unknown_id_stops_before_accessing_storage(service, operations, method_name):
    document_id = uuid4()
    operations.repository.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError) as raised:
        await getattr(service, method_name)(document_id)

    assert raised.value.args == (document_id,)
    assert operations.mock_calls == [call.repository.get_by_id(document_id)]


@pytest.mark.asyncio
async def test_delete_removes_record_and_file_before_commit(service, operations, document):
    operations.repository.get_by_id.return_value = document

    await service.delete_document(document.id)

    assert operations.mock_calls == [
        call.repository.get_by_id(document.id),
        call.repository.delete(document),
        call.storage.delete(document.storage_key),
        call.session.commit(),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component", "method", "expected_calls"),
    [
        ("repository", "delete", ["repository.delete"]),
        ("storage", "delete", ["repository.delete", "storage.delete"]),
        ("session", "commit", ["repository.delete", "storage.delete", "session.commit"]),
    ],
)
async def test_delete_rolls_back_when_an_operation_fails(
    service, operations, document, component, method, expected_calls
):
    error = RuntimeError("delete failed")
    operations.repository.get_by_id.return_value = document
    getattr(getattr(operations, component), method).side_effect = error

    with pytest.raises(RuntimeError) as raised:
        await service.delete_document(document.id)

    assert raised.value is error
    assert [entry[0] for entry in operations.mock_calls] == [
        "repository.get_by_id",
        *expected_calls,
        "session.rollback",
    ]
