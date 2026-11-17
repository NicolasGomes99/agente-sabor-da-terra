from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from google.cloud.storage import Bucket, Client
from sqlalchemy.ext.asyncio import AsyncSession

from api import dependencies
from api.dependencies import (
    get_current_user,
    get_document_service,
    get_document_storage,
)
from api.models.user import User
from api.services.auth import AuthService, InvalidAccessTokenError
from api.storage.base import DocumentStorage
from api.storage.gcs import GCSDocumentStorage
from api.storage.local import LocalDocumentStorage


def test_get_document_storage_selects_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("DOCUMENT_STORAGE_BUCKET", raising=False)

    storage = get_document_storage()

    assert isinstance(storage, LocalDocumentStorage)
    assert storage.directory == tmp_path.resolve()


def test_get_document_storage_selects_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "gcs")
    monkeypatch.setenv("DOCUMENT_STORAGE_BUCKET", "documents-bucket")
    monkeypatch.delenv("DOCUMENT_STORAGE_DIR", raising=False)
    bucket = Mock(spec=Bucket)
    client = Mock(spec=Client)
    client.bucket.return_value = bucket
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(dependencies, "Client", client_factory)

    storage = get_document_storage()

    assert isinstance(storage, GCSDocumentStorage)
    assert storage.bucket is bucket
    client_factory.assert_called_once_with()
    client.bucket.assert_called_once_with("documents-bucket")


def test_get_document_service_injects_session_and_storage() -> None:
    session = Mock(spec=AsyncSession)
    storage = Mock(spec=DocumentStorage)

    service = get_document_service(session, storage)

    assert service.repository.session is session
    assert service.storage is storage


@pytest.mark.asyncio
async def test_get_current_user_returns_authenticated_user() -> None:
    user = User(
        id=uuid4(),
        email="employee@example.com",
        password_hash="hash",
    )
    auth_service = Mock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(return_value=user)

    result = await get_current_user("valid-token", auth_service)

    assert result is user
    auth_service.get_current_user.assert_awaited_once_with("valid-token")


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_token() -> None:
    auth_service = Mock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(
        side_effect=InvalidAccessTokenError("invalid token")
    )

    with pytest.raises(HTTPException) as exception:
        await get_current_user("invalid-token", auth_service)

    assert exception.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exception.value.detail == "Could not validate credentials."
    assert exception.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_user() -> None:
    auth_service = Mock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exception:
        await get_current_user("valid-token", auth_service)

    assert exception.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exception.value.detail == "Could not validate credentials."
    assert exception.value.headers == {"WWW-Authenticate": "Bearer"}
