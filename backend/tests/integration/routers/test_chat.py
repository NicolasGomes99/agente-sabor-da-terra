from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import fastapi_app as app
from api.database import get_db
from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"


@pytest_asyncio.fixture(loop_scope="function")
async def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


async def create_user_headers(db_session: AsyncSession) -> dict[str, str]:
    """Cria um usuário no banco de teste e devolve o header com o JWT dele."""
    repository = UserRepository(db_session)
    auth_service = AuthService(
        UserService(repository),
        secret_key=TEST_SECRET_KEY,
    )
    user = await repository.create(
        f"{uuid4()}@example.com",
        auth_service.hash_password("password"),
    )
    token = auth_service.create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_session_and_register_message(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)

    created = await client.post("/chat/sessions", headers=headers)
    assert created.status_code == 201
    session_id = created.json()["id"]

    sent = await client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Quais pedidos estão pendentes?"},
    )
    assert sent.status_code == 201
    assert sent.json()["content"] == "Quais pedidos estão pendentes?"


@pytest.mark.asyncio
async def test_reopen_session_returns_messages_in_order(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = (await client.post("/chat/sessions", headers=headers)).json()["id"]

    for text in ["primeira", "segunda", "terceira"]:
        await client.post(
            f"/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"content": text},
        )

    response = await client.get(f"/chat/sessions/{session_id}", headers=headers)

    assert response.status_code == 200
    contents = [m["content"] for m in response.json()["messages"]]
    assert contents == ["primeira", "segunda", "terceira"]


@pytest.mark.asyncio
async def test_session_shows_only_its_own_messages(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_a = (await client.post("/chat/sessions", headers=headers)).json()["id"]
    session_b = (await client.post("/chat/sessions", headers=headers)).json()["id"]

    await client.post(
        f"/chat/sessions/{session_a}/messages",
        headers=headers,
        json={"content": "mensagem da A"},
    )
    await client.post(
        f"/chat/sessions/{session_b}/messages",
        headers=headers,
        json={"content": "mensagem da B"},
    )

    response = await client.get(f"/chat/sessions/{session_a}", headers=headers)

    contents = [m["content"] for m in response.json()["messages"]]
    assert contents == ["mensagem da A"]


@pytest.mark.asyncio
async def test_requests_without_valid_jwt_are_rejected(
    client: httpx.AsyncClient,
) -> None:
    no_token = await client.get("/chat/sessions")
    bad_token = await client.get(
        "/chat/sessions", headers={"Authorization": "Bearer token-invalido"}
    )
    post_no_token = await client.post(
        f"/chat/sessions/{uuid4()}/messages", json={"content": "oi"}
    )

    assert no_token.status_code == 401
    assert bad_token.status_code == 401
    assert post_no_token.status_code == 401


@pytest.mark.asyncio
async def test_cannot_open_another_users_session(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    owner = await create_user_headers(db_session)
    intruder = await create_user_headers(db_session)
    session_id = (await client.post("/chat/sessions", headers=owner)).json()["id"]

    response = await client.get(f"/chat/sessions/{session_id}", headers=intruder)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_empty_message_is_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = (await client.post("/chat/sessions", headers=headers)).json()["id"]

    response = await client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": ""},
    )

    assert response.status_code == 422