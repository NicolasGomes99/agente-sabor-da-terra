from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_create_persists_normalized_user(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    user = await repository.create(
        "  Employee@Example.COM ",
        "password-hash",
    )

    assert user.id is not None
    assert user.email == "employee@example.com"
    assert user.password_hash == "password-hash"


@pytest.mark.asyncio
async def test_get_by_email_finds_user_case_insensitively(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)
    created_user = await repository.create(
        "employee@example.com",
        "password-hash",
    )

    result = await repository.get_by_email("  EMPLOYEE@EXAMPLE.COM ")

    assert result is created_user


@pytest.mark.asyncio
async def test_get_by_email_returns_none_for_unknown_email(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    result = await repository.get_by_email("unknown@example.com")

    assert result is None


@pytest.mark.asyncio
async def test_get_by_id_finds_user(db_session: AsyncSession) -> None:
    repository = UserRepository(db_session)
    created_user = await repository.create(
        "employee@example.com",
        "password-hash",
    )

    result = await repository.get_by_id(created_user.id)

    assert result is created_user


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)

    result = await repository.get_by_id(uuid4())

    assert result is None