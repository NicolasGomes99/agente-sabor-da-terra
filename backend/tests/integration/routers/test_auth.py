from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import app, fastapi_app
from api.database import get_db
from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService

pytestmark = pytest.mark.asyncio(loop_scope="session")

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"


@pytest_asyncio.fixture(loop_scope="session")
async def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    fastapi_app.dependency_overrides.clear()


async def test_login_returns_access_token(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)
    auth_service = AuthService(
        UserService(repository),
        secret_key=TEST_SECRET_KEY,
    )
    user = await repository.create(
        "employee@example.com",
        auth_service.hash_password("correct-password"),
    )

    response = await client.post(
        "/auth/login",
        json={
            "email": "employee@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["token_type"] == "bearer"
    assert auth_service.decode_access_token(response_data["access_token"]) == user.id


async def test_login_rejects_invalid_credentials(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    repository = UserRepository(db_session)
    auth_service = AuthService(
        UserService(repository),
        secret_key=TEST_SECRET_KEY,
    )
    await repository.create(
        "employee@example.com",
        auth_service.hash_password("correct-password"),
    )

    response = await client.post(
        "/auth/login",
        json={
            "email": "employee@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials."}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_login_rejects_invalid_request_body(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "", "password": ""},
    )

    assert response.status_code == 422
