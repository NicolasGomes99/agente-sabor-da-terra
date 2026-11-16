from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User


@pytest.mark.asyncio
async def test_user_persists_with_generated_uuid(
    db_session: AsyncSession,
) -> None:
    user = User(
        email="employee@example.com",
        password_hash="password-hash",
    )
    db_session.add(user)

    await db_session.flush()
    persisted_user = await db_session.get(User, user.id)

    assert isinstance(user.id, UUID)
    assert persisted_user is not None
    assert persisted_user is user
    assert persisted_user.email == "employee@example.com"
    assert persisted_user.password_hash == "password-hash"


@pytest.mark.asyncio
async def test_user_persists_explicit_uuid(
    db_session: AsyncSession,
) -> None:
    user_id = uuid4()
    user = User(
        id=user_id,
        email="employee@example.com",
        password_hash="password-hash",
    )
    db_session.add(user)

    await db_session.flush()
    persisted_user = await db_session.get(User, user_id)

    assert persisted_user is not None
    assert persisted_user is user
    assert persisted_user.id == user_id
