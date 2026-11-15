from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.models.user import User
from api.repositories.user import UserRepository
from api.services.user import UserService


@pytest.mark.asyncio
async def test_get_by_email_delegates_to_repository() -> None:
    user = User(id=uuid4(), email="employee@example.com", password_hash="hash")
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    service = UserService(repository)

    result = await service.get_by_email("employee@example.com")

    assert result is user
    repository.get_by_email.assert_awaited_once_with("employee@example.com")


@pytest.mark.asyncio
async def test_get_by_id_delegates_to_repository() -> None:
    user_id = uuid4()
    user = User(id=user_id, email="employee@example.com", password_hash="hash")
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_id.return_value = user
    service = UserService(repository)

    result = await service.get_by_id(user_id)

    assert result is user
    repository.get_by_id.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_create_user_delegates_to_repository() -> None:
    user = User(id=uuid4(), email="employee@example.com", password_hash="hash")
    repository = AsyncMock(spec=UserRepository)
    repository.create.return_value = user
    service = UserService(repository)

    result = await service.create_user("employee@example.com", "hash")

    assert result is user
    repository.create.assert_awaited_once_with("employee@example.com", "hash")
