from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from api.app import app, fastapi_app
from api.dependencies import get_auth_service
from api.models.user import User
from api.services.auth import AuthService


@pytest.fixture
def auth_service(monkeypatch: pytest.MonkeyPatch) -> Mock:
    service = Mock(spec=AuthService)
    monkeypatch.setitem(fastapi_app.dependency_overrides, get_auth_service, lambda: service)
    return service


@pytest_asyncio.fixture
async def client(auth_service: Mock) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_login_returns_access_token(
    client: httpx.AsyncClient, auth_service: Mock,
) -> None:
    user = User(
        id=uuid4(),
        email="employee@example.com",
        password_hash="hash",
    )
    auth_service.authenticate_user = AsyncMock(return_value=user)
    auth_service.create_access_token.return_value = "access-token"
    response = await client.post(
        "/auth/login",
        json={"email": "employee@example.com", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access-token",
        "token_type": "bearer",
    }
    auth_service.authenticate_user.assert_awaited_once_with(
        "employee@example.com",
        "secret",
    )
    auth_service.create_access_token.assert_called_once_with(user.id)


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(
    client: httpx.AsyncClient, auth_service: Mock
) -> None:
    auth_service.authenticate_user = AsyncMock(return_value=None)
    response = await client.post(
        "/auth/login",
        json={"email": "employee@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials."}
    assert response.headers["www-authenticate"] == "Bearer"
    auth_service.create_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_login_rejects_invalid_request_body(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "", "password": ""},
    )

    assert response.status_code == 422
