from collections.abc import AsyncIterator
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api import database
from api.app import fastapi_app as app
from api.database import get_db
from api.dependencies import get_document_storage
from api.models.chat_message import ChatMessageRole
from api.models.document import Document, DocumentChunk
from api.repositories.chat import ChatRepository
from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService
from api.storage.base import DocumentStorage

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"


@pytest_asyncio.fixture(loop_scope="function")
async def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    auth_sessions = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: auth_sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
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
    assert sent.json()["role"] == "user"
    assert await db_session.scalar(
        text("SELECT role FROM chat_messages WHERE id = :id"),
        {"id": UUID(sent.json()["id"])},
    ) == "USER"


@pytest.mark.asyncio
async def test_reopen_session_returns_messages_in_order(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = (await client.post("/chat/sessions", headers=headers)).json()["id"]

    for content in ["primeira", "segunda"]:
        await client.post(
            f"/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"content": content},
        )
    await ChatRepository(db_session).add_message(
        UUID(session_id), "terceira", role=ChatMessageRole.AGENT
    )

    response = await client.get(f"/chat/sessions/{session_id}", headers=headers)

    assert response.status_code == 200
    messages = response.json()["messages"]
    contents = [m["content"] for m in messages]
    positions = [m["position"] for m in messages]
    assert contents == ["primeira", "segunda", "terceira"]
    assert positions == [1, 2, 3]
    assert [message["role"] for message in messages] == ["user", "user", "assistant"]


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

LOTE_ROWS = {
    "LOT-2026-0094": {
        "lote_id": "LOT-2026-0094",
        "produtor_id": "P004",
        "produto": "alface",
        "quantidade": "300",
        "unidade": "unidades",
        "data_colheita": "2026-03-09",
        "data_entrega_prevista": "2026-03-11",
    },
    "LOT-2026-0095": {
        "lote_id": "LOT-2026-0095",
        "produtor_id": "P001",
        "produto": "coentro",
        "quantidade": "150",
        "unidade": "maços",
        "data_colheita": "2026-03-10",
        "data_entrega_prevista": "2026-03-12",
    },
}


async def _create_session(client: httpx.AsyncClient, headers: dict[str, str]) -> UUID:
    created = await client.post("/chat/sessions", headers=headers)
    assert created.status_code == 201
    return UUID(created.json()["id"])


async def _seed_csv_citations(
    db_session: AsyncSession, session_id: UUID
) -> tuple[UUID, dict[str, UUID]]:
    """Cria lotes.csv com um chunk por registro e uma resposta citando cada um."""
    repository = ChatRepository(db_session)
    document = Document(
        original_filename="lotes.csv", storage_key=f"test-{uuid4().hex}"
    )
    db_session.add(document)
    await db_session.flush()
    document_id = document.id

    message_ids: dict[str, UUID] = {}
    for record_id, fields in LOTE_ROWS.items():
        chunk = DocumentChunk(
            document_id=document_id,
            content="; ".join(f"{k}={v}" for k, v in fields.items()),
            record_id=record_id,
            record_fields=fields,
        )
        db_session.add(chunk)
        await db_session.flush()
        message = await repository.add_message(
            session_id, f"Resposta sobre {record_id}", role=ChatMessageRole.AGENT
        )
        await repository.add_citation(message.id, chunk.id)
        message_ids[record_id] = message.id

    # Mesma sessão do endpoint: sem isso a coleção citations fica em cache como [].
    db_session.expire_all()
    return document_id, message_ids


@pytest.mark.asyncio
async def test_new_message_has_empty_citations(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = await _create_session(client, headers)

    sent = await client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Oi"},
    )

    assert sent.status_code == 201
    assert sent.json()["citations"] == []


@pytest.mark.asyncio
async def test_excerpt_citation_shows_document_name_and_excerpt(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = await _create_session(client, headers)
    repository = ChatRepository(db_session)

    document = Document(
        original_filename="politica-comercial-2026.txt",
        storage_key=f"test-{uuid4().hex}",
    )
    db_session.add(document)
    await db_session.flush()
    document_id = document.id
    chunk = DocumentChunk(
        document_id=document_id, content="Cláusula 4.2: prazo de 48 horas úteis."
    )
    db_session.add(chunk)
    await db_session.flush()
    message = await repository.add_message(
        session_id, "Prazo de 48 horas úteis.", role=ChatMessageRole.AGENT
    )
    await repository.add_citation(message.id, chunk.id)
    db_session.expire_all()

    response = await client.get(f"/chat/sessions/{session_id}", headers=headers)

    assert response.status_code == 200
    [citation] = response.json()["messages"][0]["citations"]
    assert citation["document_name"] == "politica-comercial-2026.txt"
    assert citation["chunk_content"] == "Cláusula 4.2: prazo de 48 horas úteis."
    assert citation["source_type"] == "excerpt"
    assert citation["record_id"] is None
    assert citation["view_url"] == f"/documents/{document_id}/content"
    assert citation["download_url"] == f"/documents/{document_id}/download"


@pytest.mark.asyncio
async def test_csv_citations_stay_on_their_message_and_identify_their_record(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = await _create_session(client, headers)
    document_id, message_ids = await _seed_csv_citations(db_session, session_id)

    # "Reabrir" a conversa: duas leituras devem devolver o mesmo resultado.
    for _ in range(2):
        response = await client.get(f"/chat/sessions/{session_id}", headers=headers)
        assert response.status_code == 200
        by_id = {m["id"]: m for m in response.json()["messages"]}

        for record_id, message_id in message_ids.items():
            [citation] = by_id[str(message_id)]["citations"]
            assert citation["record_id"] == record_id
            assert citation["label"] == f"lotes.csv - {record_id}"
            assert citation["source_type"] == "record"
            assert citation["document_id"] == str(document_id)
            assert citation["download_url"] == f"/documents/{document_id}/download"
            assert citation["record_fields"] == LOTE_ROWS[record_id]

    first = by_id[str(message_ids["LOT-2026-0094"])]["citations"][0]["record_fields"]
    assert first["produtor_id"] == "P004"
    assert first["quantidade"] == "300"
    assert first["produto"] == "alface"
    assert first["data_colheita"]
    assert first["data_entrega_prevista"]


@pytest.mark.asyncio
async def test_delete_is_blocked_for_cited_csv_and_reports_the_record(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = await _create_session(client, headers)
    document_id, _ = await _seed_csv_citations(db_session, session_id)
    storage = Mock(spec=DocumentStorage)
    app.dependency_overrides[get_document_storage] = lambda: storage

    response = await client.delete(f"/documents/{document_id}", headers=headers)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "lotes.csv" in detail
    assert "registro LOT-2026-009" in detail
    assert "(e mais 1)" in detail
    assert await db_session.get(Document, document_id) is not None
    storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_is_blocked_for_cited_excerpt(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    headers = await create_user_headers(db_session)
    session_id = await _create_session(client, headers)
    repository = ChatRepository(db_session)
    document = Document(
        original_filename="politica-comercial-2026.txt",
        storage_key=f"test-{uuid4().hex}",
    )
    db_session.add(document)
    await db_session.flush()
    document_id = document.id
    chunk = DocumentChunk(document_id=document_id, content="Cláusula 4.2")
    db_session.add(chunk)
    await db_session.flush()
    message = await repository.add_message(
        session_id, "Resposta", role=ChatMessageRole.AGENT
    )
    await repository.add_citation(message.id, chunk.id)
    db_session.expire_all()
    storage = Mock(spec=DocumentStorage)
    app.dependency_overrides[get_document_storage] = lambda: storage

    response = await client.delete(f"/documents/{document_id}", headers=headers)

    assert response.status_code == 409
    assert "politica-comercial-2026.txt" in response.json()["detail"]
    assert "Cláusula 4.2" in response.json()["detail"]
    assert await db_session.get(Document, document_id) is not None
    storage.delete.assert_not_called()