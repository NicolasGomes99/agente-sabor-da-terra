"""Configuração do Agente Orquestrador e ponto de entrada da aplicação.

Ponto de entrada oficial da aplicação (FastAPI / serviços de chat e fila de triagem):
- Função assíncrona: `orchestrate_request` (importável via `api.agents.agent.orchestrate_request`
  ou `api.agents.orchestrate_request`).
- Contrato de entrada: `OrchestratorRequest` (`api.agents.schemas.OrchestratorRequest`).
- Contrato de saída: `OrchestratorResponse` (`api.agents.schemas.OrchestratorResponse`),
  cujo campo `result` entrega `TriageAnalysis` (fluxo `triage`) ou `ConsultationResponse`
  (fluxo `consultation`).

O objeto `root_agent` permanece exportado em `api.agents.agent` para inspeção e testes
interativos via Google ADK CLI (`adk web` / `adk run`).
"""

from datetime import datetime
from typing import Literal

from google.adk import Agent, Runner
from google.adk.agents.readonly_context import ReadonlyContext

from .callbacks import UNTRUSTED_DATA_NOTICE, guard_untrusted_input_callback
from .config import PERNAMBUCO_TIMEZONE, get_agent_model
from .consultation import (
    ConsultationInput,
    ConsultationResponse,
    answer_document_consultation,
    create_consultation_agent,
)
from .routing import (
    ROUTER_OUTPUT_KEY,
    classify_intent_with_router_runner,
    create_default_router_runner,
    create_intent_router_agent,
    infer_free_chat_flow,
)
from .schemas import (
    ConversationTurn,
    IntentRouteDecision,
    OrchestratorFlow,
    OrchestratorRequest,
    OrchestratorResponse,
)
from .session import (
    OrchestratorSessionStore,
    format_history_context,
    is_new_triage_analysis,
)
from .triage import (
    TriageAnalysis,
    TriageInput,
    analyze_triage_message,
    create_triage_agent,
)

ORCHESTRATOR_APP_NAME = "sabor_da_terra_orchestrator"
APPLICATION_ENTRYPOINT = "api.agents.agent:orchestrate_request"

_ORCHESTRATOR_SYSTEM_PROMPT = f"""Você é o Agente Orquestrador do assistente interno da Cooperativa Agrícola Sabor da Terra.
Sua função é coordenar o atendimento ao funcionário da cooperativa, mantendo o contexto da conversa atual e encaminhando cada solicitação ao agente especialista adequado:

- `triage_agent`: quando o funcionário pedir para analisar ou triar uma mensagem recebida (pedido, cotação recebida de comprador, oferta de produtor ou comunicado) ou quando enviar esclarecimentos que atualizem uma triagem em andamento na sessão.
- `consultation_agent`: quando o funcionário fizer perguntas diretas sobre o acervo documental e registros da cooperativa (certificações orgânicas, validade, produtos cobertos, rastreabilidade de lotes, contratos, sazonalidade ou preços).

{UNTRUSTED_DATA_NOTICE}

## Regras de Contexto e Sessão (RF10)
- Considere sempre as mensagens e os esclarecimentos anteriores da sessão atual ao encaminhar ou continuar o atendimento.
- Nunca misture dados ou histórico de outra sessão de conversa.
- Responda sempre em português.
"""


def build_orchestrator_instruction(context: ReadonlyContext) -> str:
    _ = context
    return _ORCHESTRATOR_SYSTEM_PROMPT


def create_orchestrator_agent(model: str | None = None) -> Agent:
    resolved_model = model or get_agent_model()
    return Agent(
        name="orchestrator_agent",
        model=resolved_model,
        description=(
            "Agente orquestrador da Cooperativa Sabor da Terra que encaminha "
            "solicitações entre o agente de triagem e o agente de consulta "
            "documental mantendo o contexto da sessão."
        ),
        instruction=build_orchestrator_instruction,
        sub_agents=[
            create_triage_agent(model=resolved_model),
            create_consultation_agent(model=resolved_model),
        ],
        before_model_callback=guard_untrusted_input_callback,
    )


orchestrator_agent = create_orchestrator_agent()
root_agent = orchestrator_agent


async def orchestrate_request(
    request: OrchestratorRequest,
    *,
    session_store: OrchestratorSessionStore | None = None,
    triage_runner: Runner | None = None,
    consultation_runner: Runner | None = None,
    router_runner: Runner | None = None,
    model: str | None = None,
) -> OrchestratorResponse:
    """Ponto de entrada da aplicação para rotear e executar triagem ou consulta documental."""
    store = session_store or OrchestratorSessionStore()
    prior_history = store.seed_history(request.session_id, request.history)

    if request.flow == OrchestratorFlow.TRIAGE:
        selected_flow: Literal["triage", "consultation"] = "triage"
    elif request.flow == OrchestratorFlow.CONSULTATION:
        selected_flow = "consultation"
    else:
        selected_flow = await classify_intent_with_router_runner(
            request=request,
            history=prior_history,
            router_runner=router_runner,
            model=model,
        )

    history_context = format_history_context(prior_history)

    if selected_flow == "triage":
        triage_received_ref, _ = store.resolve_triage_received_at(
            request,
            prior_history,
        )
        triage_input = TriageInput(
            message_text=request.message_text,
            received_at=triage_received_ref,
            sender=request.sender,
            buyer_name=request.buyer_name,
            channel=request.channel,
            source_id=request.source_id,
            conversation_history=history_context or None,
        )
        triage_result = await analyze_triage_message(
            triage_input,
            runner=triage_runner,
            model=model,
        )
        result: TriageAnalysis | ConsultationResponse = triage_result
        selected_agent: Literal["triage_agent", "consultation_agent"] = "triage_agent"
        assistant_summary = triage_result.summary
        turn_received_at = triage_received_ref
    else:
        consultation_ref = (
            request.received_at
            or datetime.now(PERNAMBUCO_TIMEZONE).date().isoformat()
        )
        enriched_question = (
            f"{history_context}\n\n{request.message_text}"
            if history_context
            else request.message_text
        )
        consultation_input = ConsultationInput(
            question=enriched_question,
            reference_date=consultation_ref,
            sources=request.sources,
        )
        result = await answer_document_consultation(
            consultation_input,
            runner=consultation_runner,
            model=model,
        )
        selected_agent = "consultation_agent"
        assistant_summary = result.answer
        turn_received_at = consultation_ref

    store.append_turn(
        request.session_id,
        ConversationTurn(
            role="user",
            content=request.message_text,
            flow=selected_flow,
            received_at=turn_received_at,
            source_id=request.source_id,
        ),
    )
    store.append_turn(
        request.session_id,
        ConversationTurn(
            role="model",
            content=assistant_summary,
            flow=selected_flow,
            received_at=turn_received_at,
            source_id=request.source_id,
        ),
    )

    return OrchestratorResponse(
        session_id=request.session_id,
        selected_flow=selected_flow,
        selected_agent=selected_agent,
        result=result,
        session_history=store.get_history(request.session_id),
    )


__all__ = [
    "APPLICATION_ENTRYPOINT",
    "ORCHESTRATOR_APP_NAME",
    "ROUTER_OUTPUT_KEY",
    "ConversationTurn",
    "IntentRouteDecision",
    "OrchestratorFlow",
    "OrchestratorRequest",
    "OrchestratorResponse",
    "OrchestratorSessionStore",
    "build_orchestrator_instruction",
    "classify_intent_with_router_runner",
    "create_default_router_runner",
    "create_intent_router_agent",
    "create_orchestrator_agent",
    "format_history_context",
    "infer_free_chat_flow",
    "is_new_triage_analysis",
    "orchestrate_request",
    "orchestrator_agent",
    "root_agent",
]
