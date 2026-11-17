from collections.abc import AsyncIterator
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from api import app as app_module
from api.dependencies import get_current_user, get_document_service
from api.models.document import Document
from api.models.user import User
from api.services.document import DocumentNotFoundError, DocumentService

DOCUMENT_ID = uuid4()
FILENAME = "certificação.pdf"
CONTENT = b"%PDF-1.7 sample"


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
