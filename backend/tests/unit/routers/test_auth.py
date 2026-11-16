from collections.abc import Generator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import get_auth_service
from api.models.user import User
from api.services.auth import AuthService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_auth_service] = lambda: Mock(
        spec=AuthService
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_login_returns_access_token(
    client: TestClient,
) -> None:
    user = User(
        id=uuid4(),
        email="employee@example.com",
        password_hash="hash",
    )
    auth_service = Mock(spec=AuthService)
    auth_service.authenticate_user = AsyncMock(return_value=user)
    auth_service.create_access_token.return_value = "access-token"
    app.dependency_overrides[get_auth_service] = lambda: auth_service

    response = client.post(
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


def test_login_rejects_invalid_credentials(client: TestClient) -> None:
    auth_service = Mock(spec=AuthService)
    auth_service.authenticate_user = AsyncMock(return_value=None)
    app.dependency_overrides[get_auth_service] = lambda: auth_service

    response = client.post(
        "/auth/login",
        json={"email": "employee@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials."}
    assert response.headers["www-authenticate"] == "Bearer"
    auth_service.create_access_token.assert_not_called()


def test_login_rejects_invalid_request_body(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "", "password": ""},
    )

    assert response.status_code == 422
