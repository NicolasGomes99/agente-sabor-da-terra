from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from api.agents import (
    IntentRouteDecision,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorSessionStore,
    create_intent_router_agent,
    create_orchestrator_agent,
    format_history_context,
    infer_free_chat_flow,
    orchestrate_request,
    root_agent,
)
from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    ConsultationResponse,
    ConsultationSourceItem,
)
from api.agents.triage import TRIAGE_OUTPUT_KEY, TriageAnalysis


class FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"session-{len(self.sessions) + 1}",
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


class FakeSpecialistRunner:
    def __init__(
        self,
        state_key: str,
        payload: dict[str, Any],
    ) -> None:
        self.app_name = f"fake_{state_key}"
        self.session_service = FakeSessionService()
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
        prompt_text = new_message.parts[0].text
        self.received_prompts.append(prompt_text)

        import json

        session = self.session_service.sessions[session_id]
        session.state[self._state_key] = self._payload
        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(self._payload, ensure_ascii=False))],
            ),
            is_final_response=lambda: True,
        )


def test_root_agent_exposes_triage_and_consultation_sub_agents() -> None:
    agent = create_orchestrator_agent(model="gemini-3.5-flash")
    assert agent.name == "orchestrator_agent"
    assert root_agent.name == "orchestrator_agent"
    sub_agent_names = [sub.name for sub in agent.sub_agents]
    assert sub_agent_names == ["triage_agent", "consultation_agent"]

    router_agent = create_intent_router_agent(model="gemini-3.5-flash")
    assert router_agent.output_schema is IntentRouteDecision


def test_infer_free_chat_flow_routes_certification_and_order_messages() -> None:
    cert_req = OrchestratorRequest(
        session_id="sess-1",
        message_text="Quais produtores têm certificação orgânica vigente para mel?",
    )
    assert infer_free_chat_flow(cert_req, []) == "consultation"

    triage_req = OrchestratorRequest(
        session_id="sess-2",
        message_text=(
            "Analise esta mensagem de pedido: Preciso de 30kg de queijo coalho "
            "e 10kg de manteiga pra sexta."
        ),
    )
    assert infer_free_chat_flow(triage_req, []) == "triage"


@pytest.mark.asyncio
async def test_free_chat_certification_question_routes_to_consultation_agent() -> None:
    # Critério 1 da #16: pergunta sobre certificação no chat livre vai para o agente da #14
    consultation_payload = {
        "answer": (
            "Considerando a data de referência 30/10/2026, José Antônio dos Santos (P002) "
            "possui certificação orgânica vigente (ORG-PE-2025-003198) até 20/03/2027."
        ),
        "reference_date_used": "2026-10-30",
        "source_ids": ["chunk-cert-p002"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }
    consultation_runner = FakeSpecialistRunner(
        CONSULTATION_OUTPUT_KEY,
        consultation_payload,
    )
    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, {})

    request = OrchestratorRequest(
        session_id="chat-cert-01",
        message_text="A certificação orgânica de José Antônio para mel está vigente?",
        received_at="2026-10-30",
        sources=[
            ConsultationSourceItem(
                source_id="chunk-cert-p002",
                document_id="doc-p002",
                document_name="cert_organica_jose_santos_P002.txt",
                reference_label="ORG-PE-2025-003198",
                content="Certificado válido até 20/03/2027 para mel silvestre.",
            )
        ],
    )

    response = await orchestrate_request(
        request,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert response.selected_flow == "consultation"
    assert response.selected_agent == "consultation_agent"
    assert isinstance(response.result, ConsultationResponse)
    assert response.result.source_ids == ["chunk-cert-p002"]
    assert len(triage_runner.received_prompts) == 0
    assert len(consultation_runner.received_prompts) == 1


@pytest.mark.asyncio
async def test_free_chat_order_analysis_routes_to_triage_agent() -> None:
    # Critério 2 da #16: pedir no chat livre a análise de uma mensagem de pedido
    # retorna o resultado do agente de triagem da #13
    triage_payload = {
        "summary": "Pedido de 10 kg de queijo coalho e 5 kg de manteiga para sábado (31/10/2026).",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",
        "urgency_reason": "Entrega prevista para 31/10/2026, após o dia seguinte ao recebimento.",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Dona Cremilda - Lanchonete da Feira",
            "delivery_date_start": "2026-10-31",
            "items": [
                {"product": "Queijo coalho", "quantity": 10, "unit": "kg"},
                {"product": "Manteiga", "quantity": 5, "unit": "kg"},
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }
    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload)
    consultation_runner = FakeSpecialistRunner(CONSULTATION_OUTPUT_KEY, {})

    request = OrchestratorRequest(
        session_id="chat-triage-01",
        message_text=(
            "Analise esta mensagem de pedido: lucia minha filha me manda 10kg "
            "de queijo coalho e 5kg de manteiga pra sabado"
        ),
        received_at="2026-10-28T15:40:00",
    )

    response = await orchestrate_request(
        request,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert response.selected_flow == "triage"
    assert response.selected_agent == "triage_agent"
    assert isinstance(response.result, TriageAnalysis)
    assert response.result.extracted_data.delivery_date_start == "2026-10-31"
    assert len(consultation_runner.received_prompts) == 0


@pytest.mark.asyncio
async def test_queue_task_with_explicit_triage_flow_executes_triage_directly() -> None:
    # Critério 3 da #16: tarefa da fila com fluxo de triagem indicado pelo backend
    # executa esse fluxo mesmo que o texto mencione 'certificação' ou 'lote'
    triage_payload = {
        "summary": "Notificação oficial da ADAGRO sobre inspeção sanitária em 11 e 12/11/2026.",
        "request_type": "comunicado",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "indeterminada",
        "urgency_reason": "Comunicado oficial de inspeção programada sem entrega de produtos.",
        "received_date_reference": "2026-10-30",
        "extracted_data": {
            "buyer_name": "ADAGRO - Agência de Defesa Agropecuária",
            "requested_documents_or_sensitive_data": [
                "Certificações orgânicas vigentes",
                "Registro de rastreabilidade dos últimos 3 lotes",
            ],
        },
        "pending_items": [],
        "requires_clarification": True,
    }
    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload)
    consultation_runner = FakeSpecialistRunner(CONSULTATION_OUTPUT_KEY, {})

    queue_request = OrchestratorRequest(
        session_id="queue-ped-2026-014",
        flow=OrchestratorFlow.TRIAGE,
        source_id="PED-2026-014",
        received_at="2026-10-30T13:30:00",
        message_text=(
            "NOTIFICAÇÃO: solicitamos certificações orgânicas vigentes e "
            "rastreabilidade dos últimos 3 lotes para inspeção sanitária."
        ),
    )

    response = await orchestrate_request(
        queue_request,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert response.selected_flow == "triage"
    assert response.selected_agent == "triage_agent"
    assert isinstance(response.result, TriageAnalysis)
    assert response.result.request_type.value == "comunicado"
    assert len(consultation_runner.received_prompts) == 0


@pytest.mark.asyncio
async def test_resumed_session_receives_history_and_keeps_sessions_isolated() -> None:
    # Critério 4 da #16 + RF10: ao retomar uma conversa, o agente recebe o histórico
    # da sessão aberta, e conversas diferentes mantêm contextos separados
    store = OrchestratorSessionStore()

    triage_payload_turn1 = {
        "summary": "Pedido com data conflitante entre sexta-feira (30/10) e 01/11.",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "indeterminada",
        "urgency_reason": "Conflito de data de entrega.",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Restaurante Raízes",
            "has_date_conflict": True,
            "date_conflict_description": "Sexta é 30/10/2026, mas 01/11/2026 é domingo.",
            "items": [{"product": "Queijo coalho", "quantity": 30, "unit": "kg"}],
        },
        "pending_items": [],
        "requires_clarification": True,
    }
    triage_payload_turn2 = {
        "summary": "Pedido do Restaurante Raízes com entrega esclarecida para 30/10/2026.",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",
        "urgency_reason": "Entrega em 30/10/2026, após o dia seguinte ao recebimento (28/10/2026).",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Restaurante Raízes",
            "delivery_date_start": "2026-10-30",
            "has_date_conflict": False,
            "items": [{"product": "Queijo coalho", "quantity": 30, "unit": "kg"}],
        },
        "pending_items": [],
        "requires_clarification": False,
    }
    consultation_payload_other_session = {
        "answer": "Na data de referência 30/10/2026, o lote LOT-2026-0094 tem 300 unidades de alface.",
        "reference_date_used": "2026-10-30",
        "source_ids": ["rec-lot-0094"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }

    triage_runner_1 = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload_turn1)
    await orchestrate_request(
        OrchestratorRequest(
            session_id="session-A",
            flow=OrchestratorFlow.TRIAGE,
            received_at="2026-10-28T09:15:00",
            message_text="Preciso pra essa sexta (01/nov): 30kg de queijo coalho.",
        ),
        session_store=store,
        triage_runner=triage_runner_1,
    )

    # Sessão B independente (consulta documental)
    consult_runner_b = FakeSpecialistRunner(
        CONSULTATION_OUTPUT_KEY,
        consultation_payload_other_session,
    )
    resp_b = await orchestrate_request(
        OrchestratorRequest(
            session_id="session-B",
            received_at="2026-10-30",
            message_text="Qual a quantidade registrada no lote LOT-2026-0094?",
            sources=[
                ConsultationSourceItem(
                    source_id="rec-lot-0094",
                    document_name="lotes.csv",
                    content="LOT-2026-0094: 300 unidades de alface.",
                )
            ],
        ),
        session_store=store,
        consultation_runner=consult_runner_b,
    )

    # Retoma a Sessão A com uma resposta de esclarecimento curta (sem palavras-chave óbvias):
    # O orquestrador deve manter o fluxo 'triage' pelo histórico de session-A e passar o histórico
    # de session-A sem nada da session-B!
    triage_runner_2 = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload_turn2)
    resp_a_resumed = await orchestrate_request(
        OrchestratorRequest(
            session_id="session-A",
            received_at="2026-10-28T09:15:00",
            message_text="O comprador confirmou que a entrega é na sexta-feira, 30/10/2026.",
        ),
        session_store=store,
        triage_runner=triage_runner_2,
    )

    assert resp_a_resumed.selected_flow == "triage"
    assert len(resp_a_resumed.session_history) == 4
    assert len(resp_b.session_history) == 2

    prompt_sent_on_resume = triage_runner_2.received_prompts[0]
    assert "<historico_sessao_atual>" in prompt_sent_on_resume
    assert "Preciso pra essa sexta (01/nov)" in prompt_sent_on_resume
    assert "LOT-2026-0094" not in prompt_sent_on_resume
    assert format_history_context([]) == ""


def test_orchestrator_schema_is_compatible_with_google_genai_transformer() -> None:
    from google.genai._transformers import t_schema

    schema = t_schema(None, IntentRouteDecision)
    assert schema is not None
