from asyncio import (
    CancelledError,
    Event,
    create_task,
    get_running_loop,
    sleep,
    wait_for,
)
from io import BytesIO
from threading import Event as ThreadEvent
from unittest.mock import Mock, call
from uuid import uuid4
from api.models.chat_message import ChatMessage
from api.models.chat_session import ChatSession
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk
from api.services.document import (
    DocumentCitedError,
    DocumentNotFoundError,
    DocumentService,
)
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
@pytest.mark.parametrize("secondary_failure", [None, "rollback", "cleanup"])
async def test_create_rolls_back_and_cleans_up_after_insert_failure(
    service, operations, document, secondary_failure, caplog
):
    error = RuntimeError("insert failed")
    operations.repository.create.side_effect = error
    if secondary_failure == "rollback":
        operations.session.rollback.side_effect = RuntimeError("rollback failed")
    if secondary_failure == "cleanup":
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
    if secondary_failure == "rollback":
        assert "Failed to roll back document transaction" in caplog.text
    if secondary_failure == "cleanup":
        assert "Failed to clean up document file" in caplog.text


@pytest.mark.asyncio
async def test_create_preserves_file_after_commit_failure(service, operations, document, caplog):
    error = RuntimeError("commit failed")
    operations.session.commit.side_effect = error

    with BytesIO(b"content") as source, pytest.raises(RuntimeError) as raised:
        await service.create_document(document.original_filename, source)

    assert raised.value is error
    key = operations.storage.save.call_args.args[0]
    assert operations.mock_calls == [
        call.storage.save(key, source),
        call.repository.create(document.original_filename, key),
        call.session.commit(),
        call.session.rollback(),
    ]
    assert key in caplog.text


@pytest.mark.asyncio
async def test_prepare_document_read_defers_storage_open(service, operations, document):
    operations.repository.get_by_id.return_value = document

    with BytesIO(b"content") as reader:
        operations.storage.open.return_value = reader
        filename, open_reader = await service.prepare_document_read(document.id)
        assert filename == document.original_filename
        operations.storage.open.assert_not_called()
        assert open_reader() is reader
        assert not reader.closed

    assert operations.mock_calls == [
        call.repository.get_by_id(document.id),
        call.storage.open(document.storage_key),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["prepare_document_read", "delete_document"])
async def test_unknown_id_stops_before_accessing_storage(service, operations, method_name):
    document_id = uuid4()
    operations.repository.get_by_id.return_value = None

    with pytest.raises(DocumentNotFoundError) as raised:
        await getattr(service, method_name)(document_id)

    assert raised.value.args == (document_id,)
    assert operations.mock_calls == [call.repository.get_by_id(document_id)]


@pytest.mark.asyncio
async def test_delete_commits_record_before_removing_file(service, operations, document):
    operations.repository.get_by_id.return_value = document

    await service.delete_document(document.id)

    assert operations.mock_calls == [
        call.repository.get_by_id(document.id),
        call.repository.list_citations_by_document(document.id),
        call.repository.delete(document),
        call.session.commit(),
        call.storage.delete(document.storage_key),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component", "method", "expected_calls"),
    [
        ("repository", "delete", ["repository.delete"]),
        ("session", "commit", ["repository.delete", "session.commit"]),
    ],
)
async def test_delete_preserves_file_when_database_operation_fails(
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
        "repository.list_citations_by_document",
        *expected_calls,
        "session.rollback",
    ]


@pytest.mark.asyncio
async def test_delete_logs_storage_failure_after_commit(service, operations, document, caplog):
    error = OSError("delete failed")
    operations.repository.get_by_id.return_value = document
    operations.storage.delete.side_effect = error

    with pytest.raises(OSError) as raised:
        await service.delete_document(document.id)

    assert raised.value is error
    assert operations.mock_calls == [
        call.repository.get_by_id(document.id),
        call.repository.list_citations_by_document(document.id),
        call.repository.delete(document),
        call.session.commit(),
        call.storage.delete(document.storage_key),
    ]
    assert str(document.id) in caplog.text
    assert document.storage_key in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["save", "delete"])
async def test_cancelled_write_waits_for_storage_worker(service, operations, document, operation):
    loop = get_running_loop()
    started = Event()
    release = ThreadEvent()
    finished = ThreadEvent()

    def block_storage(*args):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        if operation == "save":
            assert args[1].read() == b"content"
        finished.set()

    getattr(operations.storage, operation).side_effect = block_storage
    operations.repository.get_by_id.return_value = document

    with BytesIO(b"content") as source:
        if operation == "save":
            task = create_task(service.create_document(document.original_filename, source))
        else:
            task = create_task(service.delete_document(document.id))

        try:
            await wait_for(started.wait(), timeout=5)
            task.cancel()
            await sleep(0)
            assert not task.done()
        finally:
            release.set()
            with pytest.raises(CancelledError):
                await wait_for(task, timeout=5)

    assert finished.is_set()
    assert [entry[0] for entry in operations.mock_calls] == (
        ["storage.save", "repository.create", "session.commit"]
        if operation == "save"
        else [
            "repository.get_by_id",
            "repository.list_citations_by_document",
            "repository.delete",
            "session.commit",
            "storage.delete",
        ]
    )
@pytest.fixture
def operations() -> Mock:
    operations = Mock()
    operations.repository = Mock(spec=DocumentRepository)
    operations.session = Mock(spec=AsyncSession)
    operations.repository.session = operations.session
    operations.storage = Mock(spec=DocumentStorage)
    operations.repository.list_citations_by_document.return_value = []
    return operations

@pytest.mark.asyncio
async def test_delete_is_blocked_when_document_is_cited(service, operations, document):
    chunk = DocumentChunk(
        id=uuid4(), document_id=document.id, content="x", record_id="LOT-2026-0094"
    )
    message = ChatMessage(id=uuid4())
    chat = ChatSession(id=uuid4(), user_id=uuid4(), title="Conversa de lotes")
    citation = Citation(message_id=message.id, chunk_id=chunk.id)
    operations.repository.get_by_id.return_value = document
    operations.repository.list_citations_by_document.return_value = [
        (citation, chunk, message, chat)
    ]

    with pytest.raises(DocumentCitedError) as raised:
        await service.delete_document(document.id)

    assert "registro LOT-2026-0094" in str(raised.value)
    assert "Conversa de lotes" in str(raised.value)
    assert [entry[0] for entry in operations.mock_calls] == [
        "repository.get_by_id",
        "repository.list_citations_by_document",
    ]