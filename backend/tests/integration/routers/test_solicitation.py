from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api import database
from api.agents import OrchestratorRequest, OrchestratorResponse
from api.agents.consultation.schemas import ConsultationResponse
from api.app import fastapi_app as app
from api.database import get_db
from api.dependencies import get_agent_orchestrator
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
    auth_sessions = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: auth_sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def fake_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="consultation",
            selected_agent="consultation_agent",
            result=ConsultationResponse(
                answer=f"Resposta simulada para: {request.message_text}",
                reference_date_used="2026-11-19",
                source_ids=[],
                cited_sources=[],
                has_sufficient_data=False,
            ),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_orchestrator] = lambda: fake_orchestrator
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


def solicitation_payload(
    source_id: str,
    *,
    received_at: str = "2026-10-30",
    request_type: str = "pedido",
    delivery_start: str | None = None,
    response_deadline: str | None = None,
    document_availability_start: str | None = None,
    summary: str | None = None,
    urgency_reason: str = "A classificar.",
    pending_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    extracted_data: dict[str, Any] = {}
    if delivery_start is not None:
        extracted_data["delivery_date_start"] = delivery_start
    if response_deadline is not None:
        extracted_data["response_deadline"] = response_deadline
    if document_availability_start is not None:
        extracted_data["document_availability_date_start"] = (
            document_availability_start
        )

    return {
        "input": {
            "message_text": f"Mensagem original de {source_id}",
            "received_at": received_at,
            "sender": "Cícero",
            "channel": "whatsapp",
            "source_id": source_id,
        },
        "analysis": {
            "summary": summary or f"Resumo de {source_id}",
            "request_type": request_type,
            "urgency": "indeterminada",
            "urgency_reason": urgency_reason,
            "received_date_reference": received_at,
            "extracted_data": extracted_data,
            "pending_items": pending_items or [],
        },
    }


async def create_solicitation(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    source_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    response = await client.post(
        "/solicitations",
        headers=headers,
        json=solicitation_payload(source_id, **kwargs),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_create_solicitation_persists_triage_session_history(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    solicitation_id = uuid4()
    payload = solicitation_payload(
        "PED-2026-015",
        request_type="oferta",
        response_deadline="2026-10-31",
        summary=(
            "Retorno solicitado até 31/10/2026, dia seguinte ao recebimento."
        ),
        pending_items=[
            {
                "category": "outro",
                "description": "Confirmar se o retorno deve ser feito por telefone.",
                "question_for_staff": "Qual canal usar para responder?",
            }
        ],
    )
    assert "delivery_date_start" not in payload["analysis"]["extracted_data"]
    payload["id"] = str(solicitation_id)

    response = await client.post(
        "/solicitations",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["id"] == str(solicitation_id)
    assert created["status"] == "recebida"
    assert created["request_type"] == "oferta"
    assert created["urgency"] == "urgente"
    session_id = UUID(created["session_id"])

    owner = await db_session.scalar(
        text("SELECT user_id FROM chat_sessions WHERE id = :id"),
        {"id": session_id},
    )
    assert owner is None

    messages = (
        await db_session.execute(
            text(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id = :id ORDER BY position"
            ),
            {"id": session_id},
        )
    ).all()
    assert [role for role, _ in messages] == ["USER", "AGENT"]
    assert messages[0][1] == payload["input"]["message_text"]
    analysis_message = messages[1][1]
    assert "31/10/2026" in analysis_message
    assert "Ação: Responder" in analysis_message
    assert "Ação: Entregar" not in analysis_message
    assert "dia seguinte" in analysis_message.lower()
    assert "Pendências:" in analysis_message
    assert "Qual canal usar para responder?" in analysis_message

    private_sessions = await client.get("/chat/sessions", headers=headers)
    assert private_sessions.status_code == 200
    assert private_sessions.json() == []
    private_detail = await client.get(
        f"/chat/sessions/{session_id}",
        headers=headers,
    )
    assert private_detail.status_code == 404

    queue = await client.get("/solicitations", headers=headers)
    assert queue.status_code == 200
    assert queue.json()[0]["status"] == "recebida"


@pytest.mark.asyncio
async def test_ped_2026_015_preserves_deadline_and_reason_after_reopen(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    created = await create_solicitation(
        client,
        headers,
        "PED-2026-015",
        request_type="oferta",
        response_deadline="2026-10-31",
        summary=(
            "Retorno solicitado até 31/10/2026, dia seguinte ao recebimento."
        ),
        urgency_reason=(
            "O prazo é 31/10/2026, dia seguinte ao recebimento."
        ),
        pending_items=[
            {
                "category": "outro",
                "description": "Confirmar o canal de retorno.",
                "question_for_staff": "Responder por telefone?",
            }
        ],
    )

    first_open = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=headers,
    )
    assert first_open.status_code == 200
    assert first_open.json()["urgency"] == "urgente"
    first_messages = first_open.json()["messages"]
    analysis_content = first_messages[1]["content"]
    assert "31/10/2026" in analysis_content
    assert "Ação: Responder" in analysis_content
    assert "Ação: Entregar" not in analysis_content
    assert "Data de recebimento considerada: 30/10/2026" in analysis_content
    assert "dia seguinte ao recebimento" in analysis_content
    assert "Responder por telefone?" in analysis_content

    reopened = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "em_analise"
    assert reopened.json()["urgency"] == "urgente"
    assert reopened.json()["summary"] == created["summary"]
    assert reopened.json()["messages"] == first_messages
    assert "Ação: Responder\nPrazo: 31/10/2026" in (
        reopened.json()["messages"][1]["content"]
    )

    detail = await client.get(
        f"/solicitations/{created['id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "em_analise"
    assert detail.json()["summary"] == created["summary"]


@pytest.mark.asyncio
async def test_ped_2026_014_formats_document_availability_deadline(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    created = await create_solicitation(
        client,
        headers,
        "PED-2026-014",
        request_type="comunicado",
        document_availability_start="2026-11-11",
        summary=(
            "Disponibilizar documentos no primeiro dia da inspeção, 11/11/2026."
        ),
    )

    opened = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=headers,
    )

    assert opened.status_code == 200
    assert opened.json()["urgency"] == "normal"
    analysis_content = opened.json()["messages"][1]["content"]
    assert "Ação: Disponibilizar documentos" in analysis_content
    assert "Prazo: 11/11/2026" in analysis_content
    assert "Ação: Entregar" not in analysis_content


@pytest.mark.asyncio
async def test_open_session_transitions_to_review_and_shares_clarifications(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    reviewer_a = await create_user_headers(db_session)
    reviewer_b = await create_user_headers(db_session)
    created = await create_solicitation(client, reviewer_a, "PED-2026-016")

    first_open = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=reviewer_a,
    )
    assert first_open.status_code == 200
    first_body = first_open.json()
    assert first_body["status"] == "em_analise"
    assert first_body["read_only"] is False
    assert len(first_body["messages"]) == 2
    assert [message["role"] for message in first_body["messages"]] == [
        "user",
        "assistant",
    ]
    analysis_content = first_body["messages"][1]["content"]
    assert "Pendências:" in analysis_content

    old_get = await client.get(
        f"/solicitations/{created['id']}/session",
        headers=reviewer_b,
    )
    assert old_get.status_code == 404

    second_open = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=reviewer_b,
    )
    assert second_open.status_code == 200
    assert second_open.json()["status"] == "em_analise"
    assert len(second_open.json()["messages"]) == 2

    clarification = await client.post(
        f"/solicitations/{created['id']}/messages",
        headers=reviewer_a,
        json={"content": "Confirmado com o comprador por telefone."},
    )
    assert clarification.status_code == 201
    turn_body = clarification.json()
    assert turn_body["user_message"]["role"] == "user"
    assert turn_body["assistant_message"]["role"] == "assistant"
    assert turn_body["solicitation"]["status"] == "em_analise"

    shared = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=reviewer_b,
    )
    assert shared.status_code == 200
    contents = [message["content"] for message in shared.json()["messages"]]
    assert contents == [
        "Mensagem original de PED-2026-016",
        analysis_content,
        "Confirmado com o comprador por telefone.",
        "Resposta simulada para: Confirmado com o comprador por telefone.",
    ]
    assert shared.json()["status"] == "em_analise"


@pytest.mark.asyncio
async def test_queue_keeps_received_status_until_first_open(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    urgent = await create_solicitation(
        client,
        headers,
        "OFE-URGENTE",
        request_type="oferta",
        delivery_start="2026-10-31",
    )
    normal = await create_solicitation(
        client,
        headers,
        "PED-NORMAL",
        delivery_start="2026-11-11",
    )
    undetermined = await create_solicitation(
        client,
        headers,
        "CON-INDEFINIDA",
        request_type="consulta",
    )

    first_list = await client.get("/solicitations", headers=headers)
    assert first_list.status_code == 200
    by_id = {item["id"]: item for item in first_list.json()}
    assert by_id[urgent["id"]]["status"] == "recebida"
    assert by_id[normal["id"]]["status"] == "recebida"
    assert by_id[undetermined["id"]]["status"] == "recebida"
    assert by_id[urgent["id"]]["urgency"] == "urgente"
    assert by_id[normal["id"]]["urgency"] == "normal"
    assert by_id[undetermined["id"]]["urgency"] == "indeterminada"

    second_list = await client.get("/solicitations", headers=headers)
    assert all(item["status"] == "recebida" for item in second_list.json())

    opened = await client.post(
        f"/solicitations/{normal['id']}/open",
        headers=headers,
    )
    assert opened.status_code == 200

    third_list = await client.get("/solicitations", headers=headers)
    by_id = {item["id"]: item for item in third_list.json()}
    assert by_id[normal["id"]]["status"] == "em_analise"
    assert by_id[urgent["id"]]["status"] == "recebida"
    assert by_id[undetermined["id"]]["status"] == "recebida"


@pytest.mark.asyncio
async def test_finalize_without_service_and_reject_new_messages(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    reviewer_a = await create_user_headers(db_session)
    reviewer_b = await create_user_headers(db_session)
    created = await create_solicitation(client, reviewer_a, "PED-2026-017")

    finalized = await client.post(
        f"/solicitations/{created['id']}/finalize",
        headers=reviewer_a,
    )
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "finalizada"

    finalized_again = await client.post(
        f"/solicitations/{created['id']}/finalize",
        headers=reviewer_b,
    )
    assert finalized_again.status_code == 200
    assert finalized_again.json()["status"] == "finalizada"

    read_only = await client.post(
        f"/solicitations/{created['id']}/open",
        headers=reviewer_b,
    )
    assert read_only.status_code == 200
    assert read_only.json()["status"] == "finalizada"
    assert read_only.json()["read_only"] is True
    assert len(read_only.json()["messages"]) == 2

    rejected = await client.post(
        f"/solicitations/{created['id']}/messages",
        headers=reviewer_b,
        json={"content": "Mensagem depois do encerramento."},
    )
    assert rejected.status_code == 409

    queue = await client.get("/solicitations", headers=reviewer_b)
    assert queue.status_code == 200
    assert {item["id"]: item for item in queue.json()}[
        created["id"]
    ]["status"] == "finalizada"

    detail = await client.get(
        f"/solicitations/{created['id']}",
        headers=reviewer_b,
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "finalizada"


@pytest.mark.asyncio
async def test_private_chat_remains_owner_only_and_absent_from_queue(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await create_user_headers(db_session)
    intruder = await create_user_headers(db_session)
    session_id = (
        await client.post("/chat/sessions", headers=owner)
    ).json()["id"]

    owner_list = await client.get("/chat/sessions", headers=owner)
    assert owner_list.status_code == 200
    assert [item["id"] for item in owner_list.json()] == [session_id]
    intruder_list = await client.get("/chat/sessions", headers=intruder)
    assert intruder_list.status_code == 200
    assert intruder_list.json() == []

    intruder_read = await client.get(
        f"/chat/sessions/{session_id}",
        headers=intruder,
    )
    assert intruder_read.status_code == 404
    intruder_write = await client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=intruder,
        json={"content": "Tentativa de acesso."},
    )
    assert intruder_write.status_code == 404

    queue = await client.get("/solicitations", headers=intruder)
    assert queue.status_code == 200
    assert queue.json() == []


@pytest.mark.asyncio
async def test_solicitation_requests_without_valid_jwt_are_rejected(
    client: httpx.AsyncClient,
) -> None:
    missing_id = uuid4()
    payload = solicitation_payload("PED-2026-018")
    no_token_get = await client.get("/solicitations")
    no_token_create = await client.post("/solicitations", json=payload)
    no_token_detail = await client.get(f"/solicitations/{missing_id}")
    no_token_session = await client.post(
        f"/solicitations/{missing_id}/open"
    )
    no_token_message = await client.post(
        f"/solicitations/{missing_id}/messages",
        json={"content": "oi"},
    )
    no_token_finalize = await client.post(
        f"/solicitations/{missing_id}/finalize"
    )
    bad_token_get = await client.get(
        "/solicitations",
        headers={"Authorization": "Bearer token-invalido"},
    )

    assert no_token_get.status_code == 401
    assert no_token_create.status_code == 401
    assert no_token_detail.status_code == 401
    assert no_token_session.status_code == 401
    assert no_token_message.status_code == 401
    assert no_token_finalize.status_code == 401
    assert bad_token_get.status_code == 401
