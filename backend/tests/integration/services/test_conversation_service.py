import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from google.genai import types
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from api import database
from api.agents import (
    ROUTER_OUTPUT_KEY,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
    orchestrate_request,
)
from api.agents.config import PERNAMBUCO_TIMEZONE
from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    ConsultationResponse,
)
from api.agents.triage import TRIAGE_OUTPUT_KEY, TriageAnalysis
from api.app import fastapi_app as app
from api.database import get_db
from api.dependencies import (
    get_agent_orchestrator,
    get_document_source_provider,
    get_document_storage,
    get_triage_origin_metadata_provider,
)
from api.models.chat_message import ChatMessageRole
from api.models.chat_operation import ChatOperation, ChatOperationStatus
from api.models.chat_session import ChatSession
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk
from api.models.solicitation import (
    Solicitation,
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from api.models.user import User
from api.repositories.chat import ChatRepository
from api.repositories.document import DocumentRepository
from api.repositories.solicitation import SolicitationRepository
from api.repositories.user import UserRepository
from api.schemas.agent_integration import (
    InMemoryDocumentSourceProvider,
    PreparedTriageContext,
)
from api.schemas.solicitation import SolicitationCreate
from api.services.auth import AuthService
from api.services.conversation import (
    ConversationExecutionError,
    ConversationService,
    ConversationSolicitationFinishedError,
    InMemoryTriageOriginMetadataProvider,
    PersistedDocumentSourceProvider,
    StaleOperationResultError,
)
from api.services.solicitation import SolicitationService
from api.services.user import UserService
from api.storage.local import LocalDocumentStorage

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"


class _FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"conv-session-{len(self.sessions) + 1}",
            app_name=app_name,
            user_id=user_id,
            state={},
        )
        self.sessions[session.id] = session
        return session

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> SimpleNamespace | None:
        _ = (app_name, user_id)
        return self.sessions.get(session_id)


class _FakeRunner:
    def __init__(self, state_key: str, payload: dict[str, Any]) -> None:
        self.app_name = f"fake_{state_key}"
        self.session_service = _FakeSessionService()
        self._state_key = state_key
        self._payload = payload
        self.received_prompts: list[str] = []

    async def run_async(
        self,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[SimpleNamespace]:
        _ = user_id
        self.received_prompts.append(new_message.parts[0].text)
        session = self.session_service.sessions[session_id]
        session.state[self._state_key] = self._payload
        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(self._payload, ensure_ascii=False))],
            ),
            is_final_response=lambda: True,
        )


@pytest_asyncio.fixture(loop_scope="function")
async def api_client(
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
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="function")
def real_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def _create_user_headers(
    db_session: AsyncSession,
) -> tuple[UUID, dict[str, str]]:
    user_repo = UserRepository(db_session)
    auth_service = AuthService(UserService(user_repo), secret_key=TEST_SECRET_KEY)
    user = await user_repo.create(
        f"conv-{uuid4()}@example.com",
        auth_service.hash_password("secret-pass"),
    )
    await db_session.commit()
    token = auth_service.create_access_token(user.id)
    return user.id, {"Authorization": f"Bearer {token}"}


def _ped_2026_003_payload() -> dict[str, Any]:
    return {
        "input": {
            "message_text": "Precisamos de 20 kg de queijo coalho para amanhã cedo.",
            "received_at": "2026-10-28T09:15:00-03:00",
            "sender": "Supermercado Boa Vista",
            "channel": "whatsapp",
            "source_id": "PED-2026-003",
        },
        "analysis": {
            "summary": "Pedido de queijo coalho para 29/10/2026 com detalhes pendentes.",
            "request_type": "pedido",
            "urgency": "urgente",
            "urgency_reason": "Entrega prevista para 29/10/2026 (dia seguinte a 28/10/2026).",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "buyer_name": "Supermercado Boa Vista",
                "delivery_date_start": "2026-10-29",
                "items": [
                    {
                        "product": "Queijo coalho",
                        "quantity": 20,
                        "unit": "kg",
                    }
                ],
            },
            "pending_items": [
                {
                    "category": "outro",
                    "description": "Confirmar exigência de certificação orgânica.",
                    "question_for_staff": "O comprador exige certificação orgânica?",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_free_chat_routes_through_orchestrate_request_persists_citations_and_downloads_sources(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    # Critérios 1, 6, 7, 8, 9, 10 e 16 da #51:
    # - chat livre usa orchestrate_request (flow=AUTO) e persiste resposta + citações
    # - fontes de teste no banco permitem abrir e baixar o documento citado
    # - reabrir conversa preserva citações e mantém sessões isoladas
    # - outro usuário recebe 404 na conversa privada
    # - sem fontes disponíveis, assistente informa insuficiência de dados
    owner_id, owner_headers = await _create_user_headers(db_session)
    _, intruder_headers = await _create_user_headers(db_session)

    storage = LocalDocumentStorage(tmp_path)
    stored_key = f"politica-{uuid4().hex}.txt"
    storage.save(stored_key, BytesIO(b"Clausula 4.2: prazo maximo de 48h uteis."))
    doc = Document(
        original_filename="politica-comercial-2026.txt",
        storage_key=stored_key,
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = DocumentChunk(
        document_id=doc.id,
        content="Cláusula 4.2: prazo máximo de 48h úteis.",
    )
    db_session.add(chunk)
    await db_session.commit()

    captured_requests: list[OrchestratorRequest] = []
    fake_router = _FakeRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "consultation", "reason": "Consulta documental."},
    )
    fake_consult = _FakeRunner(
        CONSULTATION_OUTPUT_KEY,
        {
            "answer": "Considerando 19/11/2026, a política comercial prevê prazo máximo de 48h úteis.",
            "reference_date_used": "2026-11-19",
            "source_ids": [str(chunk.id)],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
    )

    async def simulated_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        captured_requests.append(request)
        return await orchestrate_request(
            request,
            session_store=None,
            router_runner=fake_router,
            consultation_runner=fake_consult,
        )

    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_agent_orchestrator] = lambda: simulated_orchestrator

    session_a = (await api_client.post("/chat/sessions", headers=owner_headers)).json()["id"]
    session_b = (await api_client.post("/chat/sessions", headers=owner_headers)).json()["id"]

    # Acesso privado bloqueado para outro usuário (AC #16)
    assert (
        await api_client.post(
            f"/chat/sessions/{session_a}/messages",
            headers=intruder_headers,
            json={"content": "Tentativa indevida"},
        )
    ).status_code == 404

    turn_resp = await api_client.post(
        f"/chat/sessions/{session_a}/messages",
        headers=owner_headers,
        json={
            "content": "Qual o prazo da política comercial?",
            "operation_id": "op-free-1",
        },
    )
    assert turn_resp.status_code == 201, turn_resp.text
    turn = turn_resp.json()
    assert turn["operation_id"] == "op-free-1"
    assert turn["selected_flow"] == "consultation"
    assert turn["user_message"]["role"] == "user"
    assert turn["assistant_message"]["role"] == "assistant"
    assert len(turn["assistant_message"]["citations"]) == 1
    citation = turn["assistant_message"]["citations"][0]
    assert citation["document_name"] == "politica-comercial-2026.txt"
    assert captured_requests[0].flow == OrchestratorFlow.AUTO

    # Abrir e baixar documento citado (AC #8)
    view_resp = await api_client.get(citation["view_url"], headers=owner_headers)
    assert view_resp.status_code == 200
    assert "48h uteis" in view_resp.text
    dl_resp = await api_client.get(citation["download_url"], headers=owner_headers)
    assert dl_resp.status_code == 200
    assert dl_resp.content == b"Clausula 4.2: prazo maximo de 48h uteis."

    # Reabrir conversa preserva citações e sessão B continua isolada (AC #6, #7, #9)
    reopened = await api_client.get(f"/chat/sessions/{session_a}", headers=owner_headers)
    assert reopened.status_code == 200
    reopened_msgs = reopened.json()["messages"]
    assert len(reopened_msgs) == 2
    assert len(reopened_msgs[1]["citations"]) == 1
    assert reopened_msgs[1]["citations"][0]["chunk_id"] == str(chunk.id)

    # Segundo turno na sessão A envia histórico persistido (sem duplicar mensagem atual)
    await api_client.post(
        f"/chat/sessions/{session_a}/messages",
        headers=owner_headers,
        json={"content": "E qual cláusula cita esse prazo?"},
    )
    assert len(captured_requests[1].history) == 2
    assert captured_requests[1].history[0].content == "Qual o prazo da política comercial?"
    assert captured_requests[1].history[1].role == "model"

    # Sessão B sem fontes disponíveis informa insuficiência de dados (AC #7, #10)
    app.dependency_overrides[get_document_source_provider] = (
        lambda: InMemoryDocumentSourceProvider()
    )
    empty_consult = _FakeRunner(
        CONSULTATION_OUTPUT_KEY,
        {
            "answer": "Não encontrei informações suficientes nas fontes disponibilizadas para responder.",
            "reference_date_used": "2026-11-19",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": False,
        },
    )

    async def empty_sources_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        assert request.history == []
        assert request.sources == []
        return await orchestrate_request(
            request,
            session_store=None,
            router_runner=fake_router,
            consultation_runner=empty_consult,
        )

    app.dependency_overrides[get_agent_orchestrator] = lambda: empty_sources_orchestrator
    empty_turn = await api_client.post(
        f"/chat/sessions/{session_b}/messages",
        headers=owner_headers,
        json={"content": "Qual o certificado do produtor P999?"},
    )
    assert empty_turn.status_code == 201
    empty_body = empty_turn.json()
    assert "dados suficientes" in empty_body["assistant_message"]["content"].lower()
    assert empty_body["assistant_message"]["citations"] == []
    _ = owner_id


@pytest.mark.asyncio
async def test_triage_ped_2026_003_in_november_preserves_oct_28_updates_card_and_supports_consultation(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    # Critérios 2, 3, 4 e 5 da #51:
    # - retoma PED-2026-003 em novembro de 2026 preservando 28/10/2026 de EntradaRecebida
    # - considera mensagem original, análise inicial e esclarecimentos anteriores
    # - atualiza resumo/tipo/urgência do cartão sem alterar o estado (em_analise)
    # - permite consulta documental no chat da triagem sem alterar o cartão
    _, headers = await _create_user_headers(db_session)
    solicitation_service = SolicitationService(SolicitationRepository(db_session))
    solicitation = await solicitation_service.create_from_analysis(
        SolicitationCreate.model_validate(_ped_2026_003_payload())
    )
    await solicitation_service.open_session(solicitation.id)

    origin_provider = InMemoryTriageOriginMetadataProvider(
        {
            solicitation.id: PreparedTriageContext(
                solicitation_id=solicitation.id,
                original_received_at="2026-10-28T09:15:00-03:00",
                source_id="PED-2026-003",
                sender="Supermercado Boa Vista",
                channel="whatsapp",
            )
        }
    )

    captured_requests: list[OrchestratorRequest] = []
    triage_runner = _FakeRunner(
        TRIAGE_OUTPUT_KEY,
        {
            "summary": "Pedido confirmado de 20 kg de queijo coalho para entrega em 05/11/2026.",
            "request_type": "pedido",
            "urgency": "normal",
            "urgency_reason": "Comprador reagendou a entrega para 05/11/2026.",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "buyer_name": "Supermercado Boa Vista",
                "delivery_date_start": "2026-11-05",
                "items": [{"product": "Queijo coalho", "quantity": 20, "unit": "kg"}],
            },
            "pending_items": [],
        },
    )
    router_triage = _FakeRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "triage", "reason": "Esclarecimento de triagem."},
    )

    async def triage_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        captured_requests.append(request)
        return await orchestrate_request(
            request,
            session_store=None,
            router_runner=router_triage,
            triage_runner=triage_runner,
        )

    app.dependency_overrides[get_triage_origin_metadata_provider] = lambda: origin_provider
    app.dependency_overrides[get_agent_orchestrator] = lambda: triage_orchestrator

    # Esclarecimento em novembro altera prazo/urgência/resumo preservando status em_analise
    triage_resp = await api_client.post(
        f"/solicitations/{solicitation.id}/messages",
        headers=headers,
        json={
            "content": "O comprador reagendou a entrega para 05/11/2026 e dispensou certificação orgânica.",
            "operation_id": "op-triage-1",
        },
    )
    assert triage_resp.status_code == 201, triage_resp.text
    body = triage_resp.json()
    assert body["selected_flow"] == "triage"
    assert body["solicitation"]["status"] == "em_analise"
    assert body["solicitation"]["urgency"] == "normal"
    assert body["solicitation"]["request_type"] == "pedido"
    assert "05/11/2026" in body["solicitation"]["summary"]
    assert "Prazo: 05/11/2026" in body["assistant_message"]["content"]

    # Valida que 28/10/2026 foi preservado na entrada do agente de triagem!
    assert "data_recebimento_referencia: 2026-10-28" in triage_runner.received_prompts[0]
    assert captured_requests[0].source_id == "PED-2026-003"
    assert captured_requests[0].sender == "Supermercado Boa Vista"
    assert len(captured_requests[0].history) == 2

    # Consulta documental dentro do chat da triagem NÃO sobrescreve o cartão
    doc = Document(
        original_filename="cert_p003.txt",
        storage_key=f"test-triage-doc-{uuid4().hex}",
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = DocumentChunk(
        document_id=doc.id,
        content="Queijaria Cícero (P003): laudo sanitário vigente até 2027.",
    )
    db_session.add(chunk)
    await db_session.commit()

    router_consult = _FakeRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "consultation", "reason": "Consulta documental."},
    )
    consult_runner = _FakeRunner(
        CONSULTATION_OUTPUT_KEY,
        {
            "answer": "O laudo sanitário da Queijaria Cícero (P003) está vigente até 2027.",
            "reference_date_used": "2026-11-19",
            "source_ids": [str(chunk.id)],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
    )

    async def consult_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        captured_requests.append(request)
        return await orchestrate_request(
            request,
            session_store=None,
            router_runner=router_consult,
            consultation_runner=consult_runner,
        )

    app.dependency_overrides[get_agent_orchestrator] = lambda: consult_orchestrator
    consult_resp = await api_client.post(
        f"/solicitations/{solicitation.id}/messages",
        headers=headers,
        json={"content": "Qual a validade do laudo sanitário da Queijaria Cícero?"},
    )
    assert consult_resp.status_code == 201
    consult_body = consult_resp.json()
    assert consult_body["selected_flow"] == "consultation"
    assert len(consult_body["assistant_message"]["citations"]) == 1
    assert consult_body["solicitation"]["summary"] == body["solicitation"]["summary"]
    assert consult_body["solicitation"]["urgency"] == "normal"
    assert consult_body["solicitation"]["status"] == "em_analise"
    # Histórico enviado à consulta incluiu a mensagem original + análise + esclarecimento + nova análise (4 turnos)
    assert len(captured_requests[1].history) == 4


@pytest.mark.asyncio
async def test_failure_preserves_user_message_and_idempotent_retry_reuses_it_without_duplicating(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    # Critérios 12 e 13 da #51:
    # - se a execução falhar, mensagem do usuário e histórico anterior permanecem intactos
    # - tentar novamente com o mesmo operation_id reutiliza a mensagem original sem duplicar
    # - repetir após conclusão devolve a resposta concluída sem duplicar nem reexecutar o agente
    _, headers = await _create_user_headers(db_session)
    session_id = (await api_client.post("/chat/sessions", headers=headers)).json()["id"]

    calls = 0

    async def flaky_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Falha temporária no provedor de IA")
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="consultation",
            selected_agent="consultation_agent",
            result=ConsultationResponse(
                answer="Resposta concluída na segunda tentativa.",
                reference_date_used="2026-11-19",
                source_ids=[],
                cited_sources=[],
                has_sufficient_data=True,
            ),
        )

    app.dependency_overrides[get_agent_orchestrator] = lambda: flaky_orchestrator

    # Tentativa 1 falha -> retorna 502 preservando user_message no banco
    first = await api_client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Consultar política de preços", "operation_id": "op-retry-1"},
    )
    assert first.status_code == 502
    first_body = first.json()
    assert first_body["operation_id"] == "op-retry-1"
    persisted_user_msg_id = first_body["user_message"]["id"]

    after_fail = await api_client.get(f"/chat/sessions/{session_id}", headers=headers)
    assert len(after_fail.json()["messages"]) == 1
    assert after_fail.json()["messages"][0]["id"] == persisted_user_msg_id

    # Tentativa 2 (retry=True) reutiliza user_message e conclui
    second = await api_client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={
            "content": "Consultar política de preços",
            "operation_id": "op-retry-1",
            "retry": True,
        },
    )
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["user_message"]["id"] == persisted_user_msg_id
    assert second_body["assistant_message"]["content"] == "Resposta concluída na segunda tentativa."
    assert calls == 2

    # Repetir a mesma operação concluída devolve exatamente o mesmo par sem chamar o agente
    third = await api_client.post(
        f"/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Consultar política de preços", "operation_id": "op-retry-1"},
    )
    assert third.status_code == 201
    assert third.json()["user_message"]["id"] == persisted_user_msg_id
    assert third.json()["assistant_message"]["id"] == second_body["assistant_message"]["id"]
    assert calls == 2

    final_history = (
        await api_client.get(f"/chat/sessions/{session_id}", headers=headers)
    ).json()["messages"]
    assert len(final_history) == 2


@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_assistant_citations_and_card_atomically(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Critério 15 da #51: se a gravação da resposta, das citações ou da atualização do cartão
    # falhar, nenhuma alteração parcial é persistida e o histórico/cartão anteriores ficam íntegros.
    solicitation_service = SolicitationService(SolicitationRepository(db_session))
    solicitation = await solicitation_service.create_from_analysis(
        SolicitationCreate.model_validate(_ped_2026_003_payload())
    )
    await solicitation_service.open_session(solicitation.id)
    solicitation_id = solicitation.id
    session_id = solicitation.session_id
    original_summary = solicitation.summary
    original_urgency = solicitation.urgency

    async def triage_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="triage",
            selected_agent="triage_agent",
            result=TriageAnalysis.model_validate(
                {
                    "summary": "RESUMO QUE NÃO DEVE SER PERSISTIDO EM CASO DE ERRO",
                    "request_type": "consulta",
                    "urgency": "normal",
                    "urgency_reason": "Prazo longo.",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {},
                    "pending_items": [],
                }
            ),
        )

    # Simula falha no meio do commit da Phase 3 (após atualizar solicitation e inserir assistant_message)
    original_commit = db_session.commit
    commit_calls = 0

    async def fail_phase3_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise RuntimeError("falha simulada no commit da fase 3")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_phase3_commit)

    service = ConversationService(
        db_session,
        orchestrator=triage_orchestrator,
    )
    with pytest.raises(ConversationExecutionError) as exc_info:
        await service.send_triage_chat_message(
            solicitation_id=solicitation_id,
            content="Esclarecimento que falha ao gravar",
            operation_id="op-atomic-1",
        )
    assert exc_info.value.operation_id == "op-atomic-1"

    # Cartão da solicitação e mensagens devem permanecer sem qualquer alteração parcial
    reloaded_sol = await SolicitationRepository(db_session).get_by_id(solicitation_id)
    assert reloaded_sol is not None
    assert reloaded_sol.summary == original_summary
    assert reloaded_sol.urgency == original_urgency
    assert reloaded_sol.status == SolicitationStatus.IN_REVIEW

    messages = await ChatRepository(db_session).list_messages(session_id)
    # 2 mensagens iniciais + 1 mensagem do usuário salva na fase 1; 0 resposta parcial do assistente
    assert len(messages) == 3
    assert [m.role for m in messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.AGENT,
        ChatMessageRole.USER,
    ]
    op = await db_session.scalar(
        select(ChatOperation).where(
            ChatOperation.session_id == session_id,
            ChatOperation.operation_key == "op-atomic-1",
        )
    )
    assert op is not None
    assert op.status == ChatOperationStatus.FAILED.value


@pytest.mark.asyncio
async def test_concurrent_duplicate_operation_deduplicates_across_real_connections(
    real_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Critério 13 da #51 (concorrência real no PostgreSQL com duas conexões):
    # duas requisições simultâneas com o mesmo operation_id geram apenas 1 mensagem do usuário,
    # 1 resposta concluída e 1 execução do agente.
    async with real_session_factory() as setup_session:
        user = User(email=f"conc-{uuid4()}@example.com", password_hash="hash")
        setup_session.add(user)
        await setup_session.flush()
        chat = ChatSession(user_id=user.id, title="Sessão concorrente")
        setup_session.add(chat)
        await setup_session.commit()
        user_id, session_id = user.id, chat.id

    agent_calls = 0
    agent_started = asyncio.Event()
    release_agent = asyncio.Event()

    async def slow_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        nonlocal agent_calls
        agent_calls += 1
        agent_started.set()
        await release_agent.wait()
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="consultation",
            selected_agent="consultation_agent",
            result=ConsultationResponse(
                answer="Resposta única deduplicada.",
                reference_date_used="2026-11-19",
                source_ids=[],
                cited_sources=[],
                has_sufficient_data=True,
            ),
        )

    async def run_request() -> Any:
        async with real_session_factory() as session:
            service = ConversationService(
                session,
                orchestrator=slow_orchestrator,
                in_flight_wait_seconds=5.0,
            )
            return await service.send_free_chat_message(
                session_id=session_id,
                user_id=user_id,
                content="Pergunta duplicada em paralelo",
                operation_id="op-concurrent-dup",
            )

    try:
        task_1 = asyncio.create_task(run_request())
        await asyncio.wait_for(agent_started.wait(), timeout=5.0)
        task_2 = asyncio.create_task(run_request())
        await asyncio.sleep(0.15)
        release_agent.set()

        res_1, res_2 = await asyncio.gather(task_1, task_2)
        assert agent_calls == 1
        assert res_1.user_message.id == res_2.user_message.id
        assert res_1.assistant_message.id == res_2.assistant_message.id

        async with real_session_factory() as verify_session:
            msgs = await ChatRepository(verify_session).list_messages(session_id)
            assert len(msgs) == 2
            assert [m.role for m in msgs] == [ChatMessageRole.USER, ChatMessageRole.AGENT]
    finally:
        async with real_session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await cleanup_session.execute(delete(User).where(User.id == user_id))
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_delayed_previous_attempt_cannot_overwrite_newer_retry_analysis_or_card(
    real_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Critério 14 da #51 (concorrência real no PostgreSQL):
    # tentativa 1 demora; tentativa 2 (retry=True) conclui com análise mais recente (urgência normal);
    # quando tentativa 1 retorna atrasada com análise antiga (urgente), é descartada sem alterar nada.
    async with real_session_factory() as setup_session:
        sol_service = SolicitationService(SolicitationRepository(setup_session))
        solicitation = await sol_service.create_from_analysis(
            SolicitationCreate.model_validate(_ped_2026_003_payload())
        )
        await sol_service.open_session(solicitation.id)
        solicitation_id = solicitation.id
        session_id = solicitation.session_id

    attempt1_started = asyncio.Event()
    release_attempt1 = asyncio.Event()

    async def slow_stale_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        attempt1_started.set()
        await release_attempt1.wait()
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="triage",
            selected_agent="triage_agent",
            result=TriageAnalysis.model_validate(
                {
                    "summary": "ANÁLISE ATRASADA DA TENTATIVA 1",
                    "request_type": "pedido",
                    "urgency": "urgente",
                    "urgency_reason": "Resultado obsoleto.",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {},
                    "pending_items": [],
                }
            ),
        )

    async def fast_current_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="triage",
            selected_agent="triage_agent",
            result=TriageAnalysis.model_validate(
                {
                    "summary": "Análise vigente da tentativa 2 (entrega reagendada).",
                    "request_type": "pedido",
                    "urgency": "normal",
                    "urgency_reason": "Entrega para semana seguinte.",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {"delivery_date_start": "2026-11-05"},
                    "pending_items": [],
                }
            ),
        )

    async def run_attempt1() -> Any:
        async with real_session_factory() as session:
            service = ConversationService(
                session,
                orchestrator=slow_stale_orchestrator,
                clock=lambda: datetime(2026, 11, 19, 15, 0, tzinfo=PERNAMBUCO_TIMEZONE),
            )
            return await service.send_triage_chat_message(
                solicitation_id=solicitation_id,
                content="Entrega reagendada para 05/11/2026.",
                operation_id="op-stale-race",
            )

    try:
        attempt1_task = asyncio.create_task(run_attempt1())
        await asyncio.wait_for(attempt1_started.wait(), timeout=5.0)

        # Nova tentativa (retry=True) supera a tentativa 1 e conclui primeiro
        async with real_session_factory() as session2:
            service2 = ConversationService(
                session2,
                orchestrator=fast_current_orchestrator,
                clock=lambda: datetime(2026, 11, 19, 15, 1, tzinfo=PERNAMBUCO_TIMEZONE),
            )
            turn2 = await service2.send_triage_chat_message(
                solicitation_id=solicitation_id,
                content="Entrega reagendada para 05/11/2026.",
                operation_id="op-stale-race",
                retry=True,
            )
        assert turn2.solicitation is not None
        assert turn2.solicitation.urgency == SolicitationUrgency.NORMAL
        assert turn2.solicitation.summary == "Análise vigente da tentativa 2 (entrega reagendada)."

        # Agora libera a tentativa 1 atrasada: deve ser rejeitada sem alterar cartão nem histórico!
        release_attempt1.set()
        with pytest.raises(StaleOperationResultError):
            await attempt1_task

        async with real_session_factory() as verify_session:
            sol = await SolicitationRepository(verify_session).get_by_id(solicitation_id)
            assert sol is not None
            assert sol.summary == "Análise vigente da tentativa 2 (entrega reagendada)."
            assert sol.urgency == SolicitationUrgency.NORMAL
            assert sol.status == SolicitationStatus.IN_REVIEW

            msgs = await ChatRepository(verify_session).list_messages(session_id)
            # 2 iniciais + 1 usuário reutilizado + 1 assistente vigente = 4 mensagens (zero duplicata/atrasada)
            assert len(msgs) == 4
            assert all("ANÁLISE ATRASADA" not in m.content for m in msgs)
    finally:
        async with real_session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(Solicitation).where(Solicitation.id == solicitation_id)
            )
            await cleanup_session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_finalizing_solicitation_during_pending_execution_blocks_late_writes(
    real_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Critério 17 da #51 (concorrência real no PostgreSQL):
    # uma solicitação finalizada durante uma execução pendente não aceita alterações decorrentes dela.
    async with real_session_factory() as setup_session:
        sol_service = SolicitationService(SolicitationRepository(setup_session))
        solicitation = await sol_service.create_from_analysis(
            SolicitationCreate.model_validate(_ped_2026_003_payload())
        )
        await sol_service.open_session(solicitation.id)
        solicitation_id = solicitation.id
        session_id = solicitation.session_id
        original_summary = solicitation.summary

    agent_started = asyncio.Event()
    release_agent = asyncio.Event()

    async def slow_triage_orchestrator(
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        agent_started.set()
        await release_agent.wait()
        return OrchestratorResponse(
            session_id=request.session_id,
            selected_flow="triage",
            selected_agent="triage_agent",
            result=TriageAnalysis.model_validate(
                {
                    "summary": "ALTERAÇÃO INDEVIDA APÓS FINALIZAÇÃO",
                    "request_type": "consulta",
                    "urgency": "normal",
                    "urgency_reason": "Teste",
                    "received_date_reference": "2026-10-28",
                    "extracted_data": {},
                    "pending_items": [],
                }
            ),
        )

    async def run_pending_turn() -> Any:
        async with real_session_factory() as session:
            service = ConversationService(
                session,
                orchestrator=slow_triage_orchestrator,
            )
            return await service.send_triage_chat_message(
                solicitation_id=solicitation_id,
                content="Esclarecimento enviado antes de finalizar",
                operation_id="op-finalize-race",
            )

    try:
        pending_task = asyncio.create_task(run_pending_turn())
        await asyncio.wait_for(agent_started.wait(), timeout=5.0)

        # Outro funcionário finaliza a solicitação enquanto o agente ainda processa
        async with real_session_factory() as finalize_session:
            await SolicitationService(
                SolicitationRepository(finalize_session)
            ).finalize(solicitation_id)

        release_agent.set()
        with pytest.raises(ConversationSolicitationFinishedError):
            await pending_task

        async with real_session_factory() as verify_session:
            sol = await SolicitationRepository(verify_session).get_by_id(solicitation_id)
            assert sol is not None
            assert sol.status == SolicitationStatus.FINISHED
            assert sol.summary == original_summary
            assert sol.request_type == SolicitationType.ORDER
            assert sol.urgency == SolicitationUrgency.URGENT

            msgs = await ChatRepository(verify_session).list_messages(session_id)
            # Nenhuma resposta do assistente foi gravada após a finalização
            assert len(msgs) == 3
            assert msgs[-1].role == ChatMessageRole.USER
            citations = await verify_session.scalar(
                select(func.count()).select_from(Citation)
            )
            assert citations == 0
    finally:
        async with real_session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(Solicitation).where(Solicitation.id == solicitation_id)
            )
            await cleanup_session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await cleanup_session.commit()


@pytest.mark.asyncio
async def test_persisted_document_source_provider_returns_empty_when_db_has_no_chunks(
    db_session: AsyncSession,
) -> None:
    provider = PersistedDocumentSourceProvider(DocumentRepository(db_session))
    result = await provider.retrieve_sources(
        context=SimpleNamespace(  # type: ignore[arg-type]
            session_id=uuid4(),
            query_text="Sem documentos",
        )
    )
    assert result.sources == []
    assert result.financial_records is None
