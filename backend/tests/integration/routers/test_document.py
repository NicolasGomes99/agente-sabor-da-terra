from collections.abc import AsyncIterator
from io import BytesIO
from tempfile import SpooledTemporaryFile
from unittest.mock import AsyncMock, Mock
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import formparsers
from starlette.requests import ClientDisconnect
from starlette.types import Message

from api import app as app_module
from api import database, dependencies
from api.database import get_db
from api.dependencies import (
    get_current_user,
    get_document_service,
    get_document_storage,
)
from api.models.document import Document
from api.models.user import User
from api.routers.document import DocumentStreamResponse
from api.services.auth import AuthService, InvalidAccessTokenError
from api.services.document import DocumentNotFoundError, DocumentService
from api.services.user import UserService
from api.storage.base import DocumentStorage

DOCUMENT_ID = uuid4()
FILENAME = "certificação.pdf"
CONTENT = b"%PDF-1.7 sample"
MULTIPART_HEADERS = {"Content-Type": "multipart/form-data; boundary=test"}
FILE_PART = (
    b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.pdf"\r\n'
    b"Content-Type: application/pdf\r\n\r\n" + CONTENT
)
MULTIPART_BODY = FILE_PART + b"\r\n--test--\r\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_upload_authenticates_before_reading_body(
    client: httpx.AsyncClient, service: Mock, monkeypatch: pytest.MonkeyPatch, token: str | None
) -> None:
    auth = Mock(spec=AuthService)
    auth.get_current_user.side_effect = InvalidAccessTokenError("invalid token")
    session = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(database, "get_session_maker", lambda: lambda: session)
    monkeypatch.setattr(dependencies, "_build_auth_service", lambda session: auth)
    headers = dict(MULTIPART_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    async def body() -> AsyncIterator[bytes]:
        pytest.fail("The unauthorized request body was read.")
        yield MULTIPART_BODY

    response = await client.post("/documents", headers=headers, content=body())

    assert response.status_code == 401
    service.create_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_upload_accepts_body_at_size_limit(
    client: httpx.AsyncClient, service: Mock, document: Document, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_MAX_BYTES", str(len(MULTIPART_BODY)))
    service.create_document.return_value = document

    response = await client.post("/documents", headers=MULTIPART_HEADERS, content=MULTIPART_BODY)

    assert response.status_code == 201
    service.create_document.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_upload_rejects_oversized_content_length_before_reading_body(
    client: httpx.AsyncClient, service: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_MAX_BYTES", str(len(MULTIPART_BODY) - 1))
    headers = {**MULTIPART_HEADERS, "Content-Length": str(len(MULTIPART_BODY))}

    async def body() -> AsyncIterator[bytes]:
        pytest.fail("The oversized request body was read.")
        yield MULTIPART_BODY

    response = await client.post("/documents", headers=headers, content=body())

    assert response.status_code == 413
    service.create_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_upload_closes_temporary_file_when_stream_exceeds_limit(
    client: httpx.AsyncClient, service: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_MAX_BYTES", str(len(MULTIPART_BODY) - 1))
    files = []

    def track_temporary_file(*args, **kwargs):
        # The parser owns this file. The test checks that the parser closes it.
        file = SpooledTemporaryFile(*args, **kwargs)  # noqa: SIM115
        files.append(file)
        return file

    temporary_file = Mock(side_effect=track_temporary_file)
    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", temporary_file)

    async def body() -> AsyncIterator[bytes]:
        yield FILE_PART
        temporary_file.assert_called_once()
        yield MULTIPART_BODY[len(FILE_PART):]

    response = await client.post("/documents", headers=MULTIPART_HEADERS, content=body())

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert files[0].closed
    service.create_document.assert_not_awaited()


def test_upload_openapi_declares_multipart_file_and_size_error() -> None:
    operation = app_module.app.openapi()["paths"]["/documents"]["post"]
    request_body = operation["requestBody"]

    assert request_body["required"] is True
    schema = request_body["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["file"]
    assert schema["properties"]["file"] == {"type": "string", "format": "binary"}
    assert "413" in operation["responses"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["content", "download"])
async def test_read_releases_database_session_before_streaming(
    monkeypatch: pytest.MonkeyPatch, document: Document, action: str
) -> None:
    user = User(id=uuid4(), email="employee@example.com", password_hash="hash")
    secret = "test-only-secret-for-document-streaming"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    token = AuthService(Mock(spec=UserService), secret_key=secret).create_access_token(user.id)
    session = Mock(spec=AsyncSession)
    session.get.return_value = document
    auth_session = AsyncMock(spec=AsyncSession)
    auth_session.__aenter__.return_value = auth_session
    auth_session.get.return_value = user
    monkeypatch.setattr(database, "get_session_maker", lambda: lambda: auth_session)
    lifecycle: list[str] = []

    async def document_database() -> AsyncIterator[AsyncSession]:
        lifecycle.append("open")
        try:
            yield session
        finally:
            lifecycle.append("close")

    class SessionCheckingReader(BytesIO):
        def read(self, size: int = -1, /) -> bytes:
            auth_session.__aexit__.assert_awaited_once()
            assert lifecycle == ["open", "close"]
            return super().read(size)

    reader = SessionCheckingReader(CONTENT)
    storage = Mock(spec=DocumentStorage)
    storage.open.return_value = reader
    app = app_module.app
    monkeypatch.setitem(app.dependency_overrides, get_db, document_database)
    monkeypatch.setitem(app.dependency_overrides, get_document_storage, lambda: storage)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/documents/{document.id}/{action}", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.content == CONTENT
    assert reader.closed
    auth_session.get.assert_awaited_once_with(User, user.id)
    session.get.assert_awaited_once_with(Document, document.id)


@pytest.mark.asyncio
async def test_stream_closes_reader_when_send_fails() -> None:
    reader = BytesIO(CONTENT * 10_000)
    response = DocumentStreamResponse(reader, FILENAME, download=True)
    sent_chunks: list[bytes] = []

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            if sent_chunks:
                raise OSError("client disconnected")
            sent_chunks.append(message["body"])

    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), send)

    assert sent_chunks
    assert reader.closed


@pytest.mark.parametrize(
    ("action", "media_types"),
    [
        ("content", {
            "application/octet-stream", "application/pdf", "image/gif",
            "image/jpeg", "image/png", "image/webp",
        }),
        ("download", {"application/octet-stream"}),
    ],
)
def test_read_openapi_declares_binary_response(
    action: str, media_types: set[str]
) -> None:
    responses = app_module.app.openapi()["paths"][f"/documents/{{document_id}}/{action}"]["get"][
        "responses"
    ]

    assert responses["200"]["content"] == {
        media_type: {"schema": {"type": "string", "format": "binary"}}
        for media_type in media_types
    }
    assert responses["200"]["headers"]["Content-Disposition"]["schema"] == {"type": "string"}
    assert "404" in responses


@pytest.fixture
def service() -> Mock:
    return Mock(spec=DocumentService)


@pytest_asyncio.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch, service: Mock
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_module.app
    monkeypatch.setitem(app.dependency_overrides, get_document_service, lambda: service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def authenticated(monkeypatch: pytest.MonkeyPatch, client: httpx.AsyncClient) -> None:
    user = User(id=uuid4(), email="employee@example.com", password_hash="hash")
    monkeypatch.setitem(app_module.app.dependency_overrides, get_current_user, lambda: user)


@pytest.fixture
def document() -> Document:
    return Document(id=DOCUMENT_ID, original_filename=FILENAME, storage_key="internal-key")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/documents"),
        ("POST", "/documents"),
        ("GET", f"/documents/{DOCUMENT_ID}/content"),
        ("GET", f"/documents/{DOCUMENT_ID}/download"),
        ("DELETE", f"/documents/{DOCUMENT_ID}"),
    ],
)
async def test_document_routes_require_token(
    client: httpx.AsyncClient, service: Mock, method: str, path: str
) -> None:
    files = {"file": (FILENAME, CONTENT)} if method == "POST" else None
    response = await client.request(method, path, files=files)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert service.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_list_documents(
    client: httpx.AsyncClient, service: Mock, document: Document
) -> None:
    service.list_documents.return_value = [document]

    response = await client.get("/documents")

    assert response.status_code == 200
    assert response.json() == [{"id": str(DOCUMENT_ID), "original_filename": FILENAME}]
    service.list_documents.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_upload_document(
    client: httpx.AsyncClient, service: Mock, document: Document
) -> None:
    async def create_document(filename, source):
        assert filename == FILENAME
        assert source.read() == CONTENT
        return document

    service.create_document.side_effect = create_document

    response = await client.post("/documents", files={"file": (FILENAME, CONTENT)})

    assert response.status_code == 201
    assert response.json() == {"id": str(DOCUMENT_ID), "original_filename": FILENAME}
    service.create_document.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
@pytest.mark.parametrize("filename", [None, "  "])
async def test_upload_rejects_missing_file_or_blank_filename(
    client: httpx.AsyncClient, service: Mock, filename: str | None
) -> None:
    files = {"file": (filename, CONTENT)} if filename is not None else None
    response = await client.post("/documents", files=files)

    assert response.status_code == 422
    service.create_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
@pytest.mark.parametrize(
    ("action", "filename", "content_type", "disposition"),
    [
        ("content", FILENAME, "application/pdf", "inline"),
        ("content", "certificado.pdf.gz", "application/octet-stream", "attachment"),
        ("content", "documento.html", "application/octet-stream", "attachment"),
        ("download", FILENAME, "application/octet-stream", "attachment"),
    ],
)
async def test_read_document_streams_content_and_closes_reader(
    client: httpx.AsyncClient,
    service: Mock,
    action: str,
    filename: str,
    content_type: str,
    disposition: str,
) -> None:
    reader = BytesIO(CONTENT * 10_000)
    service.open_document.return_value = (filename, reader)

    response = await client.get(f"/documents/{DOCUMENT_ID}/{action}")

    assert response.status_code == 200
    assert response.content == CONTENT * 10_000
    assert response.headers["content-type"] == content_type
    assert response.headers["content-disposition"] == (
        f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}"
    )
    assert reader.closed
    service.open_document.assert_awaited_once_with(DOCUMENT_ID)


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
@pytest.mark.parametrize("action", ["content", "download"])
@pytest.mark.parametrize("error", [DocumentNotFoundError, FileNotFoundError])
async def test_read_returns_404_for_missing_document_or_file(
    client: httpx.AsyncClient, service: Mock, action: str, error: type[Exception]
) -> None:
    service.open_document.side_effect = error(DOCUMENT_ID)

    response = await client.get(f"/documents/{DOCUMENT_ID}/{action}")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_read_rejects_invalid_uuid(client: httpx.AsyncClient, service: Mock) -> None:
    response = await client.get("/documents/not-a-uuid/content")

    assert response.status_code == 422
    service.open_document.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_delete_returns_empty_response(client: httpx.AsyncClient, service: Mock) -> None:
    response = await client.delete(f"/documents/{DOCUMENT_ID}")

    assert response.status_code == 204
    assert response.content == b""
    service.delete_document.assert_awaited_once_with(DOCUMENT_ID)


@pytest.mark.asyncio
@pytest.mark.usefixtures("authenticated")
async def test_delete_returns_404_for_unknown_document(
    client: httpx.AsyncClient, service: Mock
) -> None:
    service.delete_document.side_effect = DocumentNotFoundError(DOCUMENT_ID)

    response = await client.delete(f"/documents/{DOCUMENT_ID}")

    assert response.status_code == 404
