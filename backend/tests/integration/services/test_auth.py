import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService

pytestmark = pytest.mark.asyncio(loop_scope="function")


def build_auth_service(session: AsyncSession) -> AuthService:
    repository = UserRepository(session)
    user_service = UserService(repository)
    return AuthService(
        user_service,
        secret_key="test-secret-key-with-at-least-32-bytes-long",
    )


async def test_authenticate_user_returns_persisted_user(
    db_session: AsyncSession,
) -> None:
    auth_service = build_auth_service(db_session)
    user = await auth_service.users.create_user(
        "employee@example.com",
        auth_service.hash_password("correct-password"),
    )

    result = await auth_service.authenticate_user(
        "employee@example.com",
        "correct-password",
    )

    assert result is user


async def test_authenticate_user_returns_none_for_wrong_password(
    db_session: AsyncSession,
) -> None:
    auth_service = build_auth_service(db_session)
    await auth_service.users.create_user(
        "employee@example.com",
        auth_service.hash_password("correct-password"),
    )

    result = await auth_service.authenticate_user(
        "employee@example.com",
        "wrong-password",
    )

    assert result is None


async def test_get_current_user_returns_user_from_access_token(
    db_session: AsyncSession,
) -> None:
    auth_service = build_auth_service(db_session)
    user = await auth_service.users.create_user(
        "employee@example.com",
        auth_service.hash_password("correct-password"),
    )
    token = auth_service.create_access_token(user.id)

    result = await auth_service.get_current_user(token)

    assert result is user
