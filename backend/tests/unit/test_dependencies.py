from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from api.dependencies import get_current_user
from api.models.user import User
from api.services.auth import AuthService, InvalidAccessTokenError


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