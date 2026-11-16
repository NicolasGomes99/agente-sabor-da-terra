from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from api.models.user import User
from api.services.auth import (
    AuthService,
    InvalidAccessTokenError,
)
from api.services.user import UserService


def build_auth_service() -> tuple[AuthService, AsyncMock]:
    user_service = AsyncMock(spec=UserService)
    auth_service = AuthService(
        user_service,
        secret_key="test-secret-key-with-at-least-32-bytes-long",
    )
    return auth_service, user_service


def test_hash_password_can_be_verified() -> None:
    auth_service, _ = build_auth_service()

    password_hash = auth_service.hash_password("correct-password")

    assert auth_service.verify_password("correct-password", password_hash)
    assert not auth_service.verify_password("wrong-password", password_hash)


@pytest.mark.asyncio
async def test_authenticate_user_returns_user_for_valid_credentials() -> None:
    auth_service, user_service = build_auth_service()
    user = User(
        id=uuid4(),
        email="employee@example.com",
        password_hash=auth_service.hash_password("correct-password"),
    )
    user_service.get_by_email.return_value = user

    result = await auth_service.authenticate_user(
        "employee@example.com",
        "correct-password",
    )

    assert result is user
    user_service.get_by_email.assert_awaited_once_with("employee@example.com")


@pytest.mark.asyncio
async def test_authenticate_user_returns_none_for_invalid_credentials() -> None:
    auth_service, user_service = build_auth_service()
    user_service.get_by_email.return_value = None

    result = await auth_service.authenticate_user(
        "employee@example.com",
        "wrong-password",
    )

    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_returns_none_for_wrong_password() -> None:
    auth_service, user_service = build_auth_service()
    user_service.get_by_email.return_value = User(
        id=uuid4(),
        email="employee@example.com",
        password_hash=auth_service.hash_password("correct-password"),
    )

    result = await auth_service.authenticate_user(
        "employee@example.com",
        "wrong-password",
    )

    assert result is None


def test_access_token_round_trip() -> None:
    auth_service, _ = build_auth_service()
    user_id = uuid4()

    token = auth_service.create_access_token(user_id)

    assert auth_service.decode_access_token(token) == user_id


def test_decode_access_token_rejects_invalid_token() -> None:
    auth_service, _ = build_auth_service()

    with pytest.raises(InvalidAccessTokenError):
        auth_service.decode_access_token("invalid-token")


def test_decode_access_token_rejects_wrong_token_type() -> None:
    auth_service, _ = build_auth_service()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": 1,
            "exp": 4102444800,
            "type": "refresh",
        },
        auth_service.secret_key,
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        auth_service.decode_access_token(token)


def test_auth_service_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    user_service = AsyncMock(spec=UserService)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
        AuthService(user_service)
