import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from api.agents import (
    ROUTER_OUTPUT_KEY,
    IntentRouteDecision,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
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
from api.agents.triage import TRIAGE_OUTPUT_KEY, TriageAnalysis, UrgencyLevel


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
        payload: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
        store_in_state: bool = True,
    ) -> None:
        self.app_name = f"fake_{state_key}"
        self.session_service = FakeSessionService()
        self._state_key = state_key
        self._payload = payload or {}
        self._error = error
        self._store_in_state = store_in_state
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

        if self._error is not None:
            raise self._error

        session = self.session_service.sessions[session_id]
        if self._store_in_state:
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


def test_split_modules_preserve_root_agent_and_documented_entrypoint() -> None:
    # Critério 5 da #37 (Orquestração): root_agent continua acessível via api.agents.agent
    # e a entrada escolhida (orchestrate_request) pode ser importada pelo caminho documentado
    from api.agents import orchestrate_request as entrypoint_from_package
    from api.agents.agent import (
        APPLICATION_ENTRYPOINT,
    )
    from api.agents.agent import (
        orchestrate_request as entrypoint_from_agent_module,
    )
    from api.agents.agent import (
        root_agent as root_from_agent_module,
    )
    from api.agents.routing import (
        classify_intent_with_router_runner,
        create_default_router_runner,
    )
    from api.agents.routing import (
        infer_free_chat_flow as infer_from_routing,
    )
    from api.agents.schemas import (
        ConversationTurn,
    )
    from api.agents.schemas import (
        IntentRouteDecision as DecisionFromSchemas,
    )
    from api.agents.schemas import (
        OrchestratorFlow as FlowFromSchemas,
    )
    from api.agents.schemas import (
        OrchestratorRequest as RequestFromSchemas,
    )
    from api.agents.schemas import (
        OrchestratorResponse as ResponseFromSchemas,
    )
    from api.agents.session import (
        OrchestratorSessionStore as StoreFromSession,
    )
    from api.agents.session import (
        format_history_context as format_from_session,
    )

    assert root_from_agent_module is root_agent
    assert entrypoint_from_agent_module is orchestrate_request
    assert entrypoint_from_package is orchestrate_request
    assert APPLICATION_ENTRYPOINT == "api.agents.agent:orchestrate_request"
    assert DecisionFromSchemas is IntentRouteDecision
    assert FlowFromSchemas is OrchestratorFlow
    assert RequestFromSchemas is OrchestratorRequest
    assert ResponseFromSchemas is OrchestratorResponse
    assert StoreFromSession is OrchestratorSessionStore
    assert format_from_session is format_history_context
    assert infer_from_routing is infer_free_chat_flow
    assert callable(classify_intent_with_router_runner)
    assert callable(create_default_router_runner)
    assert ConversationTurn(role="user", content="Teste").role == "user"


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
async def test_simulated_classifier_routes_order_with_organic_cert_to_triage_and_validity_question_to_consultation() -> None:
    # Critérios 1 e 6 da #37 (Orquestração): com o classificador simulado, um pedido para
    # analisar uma mensagem de compra que menciona certificado orgânico segue para triagem,
    # e uma pergunta sobre a validade do certificado segue para consulta documental
    triage_payload = {
        "summary": "Pedido de mel silvestre exigindo certificado orgânico vigente.",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",
        "urgency_reason": "Entrega em 05/11/2026, após o dia seguinte ao recebimento.",
        "received_date_reference": "2026-10-30",
        "extracted_data": {
            "buyer_name": "Empório Verde",
            "delivery_date_start": "2026-11-05",
            "items": [{"product": "Mel silvestre", "quantity": 20, "unit": "kg"}],
            "requirements": [
                {"description": "Certificado orgânico vigente", "source": "mensagem"}
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }
    consultation_payload = {
        "answer": (
            "Considerando a data de referência 2026-10-30, o certificado "
            "ORG-PE-2025-003198 de José Antônio dos Santos (P002) está válido até 20/03/2027."
        ),
        "reference_date_used": "2026-10-30",
        "source_ids": ["chunk-cert-p002"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }

    triage_router = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {
            "target_flow": "triage",
            "reason": "Solicitação de análise de mensagem de compra recebida.",
        },
    )
    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload)
    consultation_runner = FakeSpecialistRunner(
        CONSULTATION_OUTPUT_KEY,
        consultation_payload,
    )

    order_with_cert_request = OrchestratorRequest(
        session_id="chat-order-with-cert",
        received_at="2026-10-30",
        message_text=(
            "Por favor, processe a mensagem de compra: 'Bom dia, queremos comprar "
            "20kg de mel silvestre para entrega em 05/11/2026 com certificado orgânico.'"
        ),
    )
    triage_resp = await orchestrate_request(
        order_with_cert_request,
        router_runner=triage_router,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert isinstance(triage_resp, OrchestratorResponse)
    assert triage_resp.selected_flow == "triage"
    assert triage_resp.selected_agent == "triage_agent"
    assert isinstance(triage_resp.result, TriageAnalysis)
    assert len(triage_router.received_prompts) == 1
    assert len(triage_runner.received_prompts) == 1
    assert len(consultation_runner.received_prompts) == 0

    consult_router = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {
            "target_flow": "consultation",
            "reason": "Pergunta direta sobre validade de certificado orgânico.",
        },
    )
    validity_question_request = OrchestratorRequest(
        session_id="chat-cert-validity",
        received_at="2026-10-30",
        message_text="Qual é a validade do certificado orgânico de José Antônio para mel?",
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
    consult_resp = await orchestrate_request(
        validity_question_request,
        router_runner=consult_router,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert isinstance(consult_resp, OrchestratorResponse)
    assert consult_resp.selected_flow == "consultation"
    assert consult_resp.selected_agent == "consultation_agent"
    assert isinstance(consult_resp.result, ConsultationResponse)
    assert consult_resp.result.source_ids == ["chunk-cert-p002"]
    assert len(consult_router.received_prompts) == 1
    assert len(consultation_runner.received_prompts) == 1


@pytest.mark.asyncio
async def test_default_flow_uses_semantic_classifier_and_falls_back_to_heuristics_on_failure_or_invalid_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Critério 2 da #37 (Orquestração): confirma que o fluxo padrão (sem router_runner
    # injetado) usa o classificador semântico e recorre à heurística quando a classificação
    # falha ou devolve uma decisão inválida
    import api.agents.routing as routing_module

    triage_payload = {
        "summary": "Pedido de 10 kg de queijo coalho para sábado (31/10/2026).",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",
        "urgency_reason": "Entrega prevista para 31/10/2026.",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "delivery_date_start": "2026-10-31",
            "items": [{"product": "Queijo coalho", "quantity": 10, "unit": "kg"}],
        },
        "pending_items": [],
        "requires_clarification": False,
    }
    consultation_payload = {
        "answer": "Considerando 2026-10-30, o certificado ORG-PE-2025-003198 está vigente.",
        "reference_date_used": "2026-10-30",
        "source_ids": ["chunk-cert-p002"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }

    # 1. Fluxo padrão usa o classificador semântico quando router_runner não é injetado
    default_semantic_router = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "triage", "reason": "Classificado semanticamente como triagem."},
    )
    monkeypatch.setattr(
        routing_module,
        "create_default_router_runner",
        lambda model=None: default_semantic_router,
    )

    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload)
    consultation_runner = FakeSpecialistRunner(
        CONSULTATION_OUTPUT_KEY,
        consultation_payload,
    )

    # Texto com "?" e "certificado" (que pela heurística pura iria para consultation),
    # provando que o classificador semântico padrão foi usado
    resp_semantic = await orchestrate_request(
        OrchestratorRequest(
            session_id="default-semantic-1",
            received_at="2026-10-28",
            message_text="Esta mensagem de comprador pede certificado orgânico para 10kg de queijo?",
        ),
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )
    assert resp_semantic.selected_flow == "triage"
    assert len(default_semantic_router.received_prompts) == 1

    # 2. Quando o classificador semântico lança exceção, recorre à heurística
    failing_router = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        error=RuntimeError("Falha simulada no modelo do classificador"),
    )
    monkeypatch.setattr(
        routing_module,
        "create_default_router_runner",
        lambda model=None: failing_router,
    )

    resp_fallback_on_error = await orchestrate_request(
        OrchestratorRequest(
            session_id="fallback-error-1",
            received_at="2026-10-30",
            message_text="A certificação orgânica de José Antônio está vigente?",
            sources=[
                ConsultationSourceItem(
                    source_id="chunk-cert-p002",
                    document_name="cert_organica_jose_santos_P002.txt",
                    content="Certificado válido até 20/03/2027.",
                )
            ],
        ),
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )
    assert resp_fallback_on_error.selected_flow == "consultation"
    assert len(failing_router.received_prompts) == 1

    # 3. Quando o classificador semântico devolve decisão inválida, recorre à heurística
    invalid_decision_router = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "fluxo_inexistente", "reason": "Saída inválida do modelo."},
    )
    monkeypatch.setattr(
        routing_module,
        "create_default_router_runner",
        lambda model=None: invalid_decision_router,
    )

    resp_fallback_on_invalid = await orchestrate_request(
        OrchestratorRequest(
            session_id="fallback-invalid-1",
            received_at="2026-10-28",
            message_text="Analise esta mensagem de pedido: preciso urgente de 10kg de queijo coalho.",
        ),
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )
    assert resp_fallback_on_invalid.selected_flow == "triage"
    assert len(invalid_decision_router.received_prompts) == 1


@pytest.mark.asyncio
async def test_explicit_backend_flow_executes_specialist_without_calling_classifier() -> None:
    # Critério 3 da #37 (Orquestração): quando o backend indica o fluxo, o orquestrador
    # executa o especialista correspondente sem chamar o classificador
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
    consultation_payload = {
        "answer": "Na data de referência 2026-10-30, o lote LOT-2026-0094 registra 300 unidades.",
        "reference_date_used": "2026-10-30",
        "source_ids": ["rec-lot-0094"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }
    router_runner = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "consultation", "reason": "Não deveria ser chamado."},
    )
    triage_runner = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload)
    consultation_runner = FakeSpecialistRunner(
        CONSULTATION_OUTPUT_KEY,
        consultation_payload,
    )

    queue_triage_request = OrchestratorRequest(
        session_id="queue-ped-2026-014",
        flow=OrchestratorFlow.TRIAGE,
        source_id="PED-2026-014",
        received_at="2026-10-30T13:30:00",
        message_text=(
            "NOTIFICAÇÃO: solicitamos certificações orgânicas vigentes e "
            "rastreabilidade dos últimos 3 lotes para inspeção sanitária."
        ),
    )

    triage_response = await orchestrate_request(
        queue_triage_request,
        router_runner=router_runner,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert triage_response.selected_flow == "triage"
    assert triage_response.selected_agent == "triage_agent"
    assert isinstance(triage_response.result, TriageAnalysis)
    assert triage_response.result.request_type.value == "comunicado"
    assert len(router_runner.received_prompts) == 0
    assert len(consultation_runner.received_prompts) == 0

    explicit_consult_request = OrchestratorRequest(
        session_id="explicit-consult-01",
        flow=OrchestratorFlow.CONSULTATION,
        received_at="2026-10-30",
        message_text="Preciso urgente saber do lote LOT-2026-0094.",
        sources=[
            ConsultationSourceItem(
                source_id="rec-lot-0094",
                document_name="lotes.csv",
                content="LOT-2026-0094: 300 unidades de alface.",
            )
        ],
    )

    consult_response = await orchestrate_request(
        explicit_consult_request,
        router_runner=router_runner,
        triage_runner=triage_runner,
        consultation_runner=consultation_runner,
    )

    assert consult_response.selected_flow == "consultation"
    assert consult_response.selected_agent == "consultation_agent"
    assert isinstance(consult_response.result, ConsultationResponse)
    assert len(router_runner.received_prompts) == 0


@pytest.mark.asyncio
async def test_resumed_triage_on_2026_10_30_from_2026_10_28_separates_history_and_keeps_2026_10_29_deadline() -> None:
    # Critério 4 da #37 (Orquestração) + RF10: ao retomar em 30/10/2026 uma conversa
    # cuja mensagem original foi recebida em 28/10/2026 e dizia “amanhã”, o histórico
    # chega separado e o prazo original permanece 29/10/2026
    store = OrchestratorSessionStore()

    triage_payload_turn1 = {
        "summary": "Pedido de 15 kg de queijo coalho para amanhã (29/10/2026), com ricota condicional.",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "urgente",
        "urgency_reason": "Entrega prevista para 2026-10-29, no dia seguinte ao recebimento (2026-10-28).",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Restaurante Raízes",
            "delivery_date_start": "2026-10-29",
            "delivery_reference_raw": "amanhã",
            "has_date_conflict": False,
            "items": [
                {"product": "Queijo coalho", "quantity": 15, "unit": "kg"},
                {
                    "product": "Ricota",
                    "quantity": 5,
                    "unit": "kg",
                    "conditional": True,
                    "condition_text": "se tiver",
                    "ambiguous_or_aggregate": True,
                },
            ],
        },
        "pending_items": [],
        "requires_clarification": True,
    }
    triage_payload_turn2 = {
        "summary": "Pedido de 15 kg de queijo coalho e 5 kg de ricota confirmados para 29/10/2026.",
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "urgente",
        "urgency_reason": "Entrega prevista para 2026-10-29, no dia seguinte ao recebimento (2026-10-28).",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Restaurante Raízes",
            "delivery_date_start": None,
            "delivery_reference_raw": "amanhã",
            "has_date_conflict": False,
            "items": [
                {"product": "Queijo coalho", "quantity": 15, "unit": "kg"},
                {"product": "Ricota", "quantity": 5, "unit": "kg", "conditional": False},
            ],
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
            message_text="Preciso pra amanhã de 15kg de queijo coalho e se tiver 5kg de ricota.",
        ),
        session_store=store,
        triage_runner=triage_runner_1,
    )

    # Sessão B independente (consulta documental)
    consult_router_b = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "consultation", "reason": "Consulta de lote."},
    )
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
        router_runner=consult_router_b,
        consultation_runner=consult_runner_b,
    )

    # Retoma a Sessão A em 30/10/2026: o histórico deve chegar separado de <mensagem_recebida>,
    # a data de recebimento da mensagem em análise deve permanecer 2026-10-28 e o prazo original
    # ("amanhã") deve continuar 2026-10-29 com urgência urgente.
    resume_router_a = FakeSpecialistRunner(
        ROUTER_OUTPUT_KEY,
        {"target_flow": "triage", "reason": "Continuação da triagem na sessão A."},
    )
    triage_runner_2 = FakeSpecialistRunner(TRIAGE_OUTPUT_KEY, triage_payload_turn2)
    clarification_text = "Confirmamos que há estoque para incluir os 5kg de ricota no pedido."
    resp_a_resumed = await orchestrate_request(
        OrchestratorRequest(
            session_id="session-A",
            received_at="2026-10-30T14:00:00",
            message_text=clarification_text,
        ),
        session_store=store,
        router_runner=resume_router_a,
        triage_runner=triage_runner_2,
    )

    assert resp_a_resumed.selected_flow == "triage"
    assert isinstance(resp_a_resumed.result, TriageAnalysis)
    assert resp_a_resumed.result.received_date_reference == "2026-10-28"
    assert resp_a_resumed.result.extracted_data.delivery_date_start == "2026-10-29"
    assert resp_a_resumed.result.urgency == UrgencyLevel.URGENT
    assert len(resp_a_resumed.session_history) == 4
    assert len(resp_b.session_history) == 2

    prompt_sent_on_resume = triage_runner_2.received_prompts[0]
    assert "data_recebimento_referencia: 2026-10-28 (quarta-feira)" in prompt_sent_on_resume
    assert "- 2026-10-29 (quinta-feira) — dia seguinte ao recebimento (amanhã)" in prompt_sent_on_resume
    assert "<historico_sessao_atual>" in prompt_sent_on_resume
    assert "Preciso pra amanhã de 15kg de queijo coalho" in prompt_sent_on_resume
    assert "LOT-2026-0094" not in prompt_sent_on_resume

    # Garante que <historico_sessao_atual> está separado e fora de <mensagem_recebida>
    received_block = prompt_sent_on_resume.split("<mensagem_recebida>", maxsplit=1)[1]
    assert received_block.strip() == f"{clarification_text}\n</mensagem_recebida>"
    assert "<historico_sessao_atual>" not in received_block
    assert format_history_context([]) == ""


def test_orchestrator_schema_is_compatible_with_google_genai_transformer() -> None:
    from google.genai._transformers import t_schema

    schema = t_schema(None, IntentRouteDecision)
    assert schema is not None
