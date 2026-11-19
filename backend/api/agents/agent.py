from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from google.adk import Agent, Runner
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types
from pydantic import BaseModel, Field, field_validator

from .callbacks import UNTRUSTED_DATA_NOTICE, guard_untrusted_input_callback
from .config import PERNAMBUCO_TIMEZONE, get_agent_model
from .consultation import (
    ConsultationInput,
    ConsultationResponse,
    ConsultationSourceItem,
    answer_document_consultation,
    create_consultation_agent,
)
from .triage import (
    TriageAnalysis,
    TriageInput,
    analyze_triage_message,
    create_triage_agent,
)

ORCHESTRATOR_APP_NAME = "sabor_da_terra_orchestrator"
ROUTER_OUTPUT_KEY = "orchestrator_route"

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

_TRIAGE_KEYWORDS: tuple[str, ...] = (
    "analise esta mensagem",
    "analisar mensagem",
    "analise a mensagem",
    "analise o pedido",
    "analisar pedido",
    "triar",
    "triagem",
    "mensagem recebida",
    "pedido recebido",
    "preciso pra",
    "preciso urgente",
    "manda 10kg",
    "quero fechar",
    "entrega terça",
    "entrega sexta",
)

_CONSULTATION_KEYWORDS: tuple[str, ...] = (
    "certificação",
    "certificacao",
    "certificado",
    "orgânico",
    "organico",
    "orgânica",
    "organica",
    "vigente",
    "validade",
    "lote",
    "lot-",
    "rastreabilidade",
    "origem",
    "laudo",
    "ficha técnica",
    "ficha tecnica",
    "adagro",
)


class OrchestratorFlow(StrEnum):
    AUTO = "auto"
    TRIAGE = "triage"
    CONSULTATION = "consultation"


class IntentRouteDecision(BaseModel):
    target_flow: Literal["triage", "consultation"] = Field(
        description="Fluxo especialista escolhido para atender à mensagem no chat livre.",
    )
    reason: str = Field(
        min_length=1,
        description="Justificativa curta em português para o encaminhamento.",
    )


class ConversationTurn(BaseModel):
    role: Literal["user", "model"] = Field(
        description="Autor do turno na sessão ('user' para funcionário, 'model' para assistente).",
    )
    content: str = Field(
        min_length=1,
        description="Texto registrado no turno da conversa.",
    )
    flow: Literal["triage", "consultation"] | None = Field(
        default=None,
        description="Fluxo executado neste turno, quando conhecido.",
    )

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank.")
        return stripped


class OrchestratorRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        description="Identificador único da sessão de conversa.",
    )
    message_text: str = Field(
        min_length=1,
        description="Mensagem enviada pelo funcionário no chat ou texto da tarefa da fila.",
    )
    flow: OrchestratorFlow = Field(
        default=OrchestratorFlow.AUTO,
        description=(
            "Fluxo a executar: 'auto' no chat livre ou 'triage'/'consultation' "
            "quando indicado pelo backend (ex.: fila de triagem)."
        ),
    )
    received_at: datetime | date | str | None = Field(
        default=None,
        description="Data/hora de recebimento da mensagem ou data de referência da consulta.",
    )
    sender: str | None = Field(default=None)
    buyer_name: str | None = Field(default=None)
    channel: str | None = Field(default=None)
    source_id: str | None = Field(default=None)
    sources: list[ConsultationSourceItem] = Field(
        default_factory=list,
        description="Trechos e registros recuperados para consulta documental.",
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico anterior da sessão aberta, quando retomada.",
    )

    @field_validator("session_id", "message_text")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank.")
        return stripped


class OrchestratorResponse(BaseModel):
    session_id: str = Field(
        description="Identificador da sessão de conversa atendida.",
    )
    selected_flow: Literal["triage", "consultation"] = Field(
        description="Fluxo especialista que processou a solicitação.",
    )
    selected_agent: Literal["triage_agent", "consultation_agent"] = Field(
        description="Nome do agente especialista acionado.",
    )
    result: TriageAnalysis | ConsultationResponse = Field(
        description="Resultado estruturado no formato definido para o fluxo selecionado.",
    )
    session_history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Histórico atualizado da sessão atual.",
    )


class OrchestratorSessionStore:
    """Mantém o histórico em memória isolado por session_id."""

    def __init__(self) -> None:
        self._history_by_session: dict[str, list[ConversationTurn]] = {}

    def get_history(self, session_id: str) -> list[ConversationTurn]:
        return list(self._history_by_session.get(session_id, []))

    def seed_history(
        self,
        session_id: str,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        existing = self._history_by_session.get(session_id)
        if not existing and turns:
            self._history_by_session[session_id] = list(turns)
        return self.get_history(session_id)

    def append_turn(self, session_id: str, turn: ConversationTurn) -> None:
        turns = self._history_by_session.setdefault(session_id, [])
        turns.append(turn)


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


def create_intent_router_agent(model: str | None = None) -> Agent:
    return Agent(
        name="intent_router_agent",
        model=model or get_agent_model(),
        description="Classifica a intenção no chat livre entre triagem e consulta documental.",
        instruction=(
            "Classifique se a mensagem do funcionário no chat livre deve ser "
            "atendida pelo fluxo 'triage' (análise/triagem de mensagem de pedido, "
            "oferta, cotação ou esclarecimento de triagem) ou 'consultation' "
            "(pergunta sobre certificações orgânicas, validade, lotes, "
            "rastreabilidade ou documentos da cooperativa)."
        ),
        output_schema=IntentRouteDecision,
        output_key=ROUTER_OUTPUT_KEY,
        before_model_callback=guard_untrusted_input_callback,
    )


orchestrator_agent = create_orchestrator_agent()
root_agent = orchestrator_agent


def format_history_context(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    lines = ["<historico_sessao_atual>"]
    for idx, turn in enumerate(history, start=1):
        author = "funcionario" if turn.role == "user" else "assistente"
        flow_attr = f' fluxo="{turn.flow}"' if turn.flow else ""
        lines.append(f'<turno ordem="{idx}" autor="{author}"{flow_attr}>')
        lines.append(turn.content)
        lines.append("</turno>")
    lines.append("</historico_sessao_atual>")
    return "\n".join(lines)


def infer_free_chat_flow(
    request: OrchestratorRequest,
    history: list[ConversationTurn],
) -> Literal["triage", "consultation"]:
    """Determina o fluxo no chat livre considerando a mensagem, as fontes e o histórico da sessão."""
    lowered = request.message_text.lower()

    has_triage_signal = any(kw in lowered for kw in _TRIAGE_KEYWORDS)
    has_consultation_signal = bool(request.sources) or any(
        kw in lowered for kw in _CONSULTATION_KEYWORDS
    )

    if has_triage_signal and not has_consultation_signal:
        return "triage"
    if has_consultation_signal and not has_triage_signal:
        return "consultation"
    if has_triage_signal and has_consultation_signal:
        if any(
            marker in lowered
            for marker in (
                "analise esta mensagem",
                "analisar mensagem",
                "analise a mensagem",
                "analise o pedido",
                "triar",
            )
        ):
            return "triage"
        return "consultation"

    for turn in reversed(history):
        if turn.flow in {"triage", "consultation"}:
            return turn.flow

    if "?" in request.message_text:
        return "consultation"
    return "triage"


async def classify_intent_with_router_runner(
    request: OrchestratorRequest,
    history: list[ConversationTurn],
    router_runner: Runner,
) -> Literal["triage", "consultation"]:
    user_id = f"user-{request.session_id}"
    session = await router_runner.session_service.create_session(
        app_name=router_runner.app_name,
        user_id=user_id,
    )
    history_block = format_history_context(history)
    prompt_parts = [p for p in (history_block, request.message_text) if p]
    message = types.Content(
        role="user",
        parts=[types.Part(text="\n\n".join(prompt_parts))],
    )

    final_text: str | None = None
    async for event in router_runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            texts = [
                part.text
                for part in event.content.parts
                if getattr(part, "text", None)
            ]
            if texts:
                final_text = "\n".join(texts).strip()

    updated_session = await router_runner.session_service.get_session(
        app_name=router_runner.app_name,
        user_id=user_id,
        session_id=session.id,
    )
    if updated_session and ROUTER_OUTPUT_KEY in updated_session.state:
        raw = updated_session.state[ROUTER_OUTPUT_KEY]
        decision = (
            raw
            if isinstance(raw, IntentRouteDecision)
            else IntentRouteDecision.model_validate(raw)
        )
        return decision.target_flow
    if final_text:
        decision = IntentRouteDecision.model_validate_json(final_text)
        return decision.target_flow

    return infer_free_chat_flow(request, history)


async def orchestrate_request(
    request: OrchestratorRequest,
    *,
    session_store: OrchestratorSessionStore | None = None,
    triage_runner: Runner | None = None,
    consultation_runner: Runner | None = None,
    router_runner: Runner | None = None,
    model: str | None = None,
) -> OrchestratorResponse:
    store = session_store or OrchestratorSessionStore()
    prior_history = store.seed_history(request.session_id, request.history)

    if request.flow == OrchestratorFlow.TRIAGE:
        selected_flow: Literal["triage", "consultation"] = "triage"
    elif request.flow == OrchestratorFlow.CONSULTATION:
        selected_flow = "consultation"
    elif router_runner is not None:
        selected_flow = await classify_intent_with_router_runner(
            request=request,
            history=prior_history,
            router_runner=router_runner,
        )
    else:
        selected_flow = infer_free_chat_flow(request, prior_history)

    history_context = format_history_context(prior_history)
    enriched_message = (
        f"{history_context}\n\n{request.message_text}"
        if history_context
        else request.message_text
    )

    if selected_flow == "triage":
        received_ref = request.received_at or datetime.now(UTC)
        triage_input = TriageInput(
            message_text=enriched_message,
            received_at=received_ref,
            sender=request.sender,
            buyer_name=request.buyer_name,
            channel=request.channel,
            source_id=request.source_id,
        )
        result: TriageAnalysis | ConsultationResponse = await analyze_triage_message(
            triage_input,
            runner=triage_runner,
            model=model,
        )
        selected_agent: Literal["triage_agent", "consultation_agent"] = "triage_agent"
        assistant_summary = result.summary
    else:
        consultation_ref = (
            request.received_at
            or datetime.now(PERNAMBUCO_TIMEZONE).date().isoformat()
        )
        consultation_input = ConsultationInput(
            question=enriched_message,
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

    store.append_turn(
        request.session_id,
        ConversationTurn(
            role="user",
            content=request.message_text,
            flow=selected_flow,
        ),
    )
    store.append_turn(
        request.session_id,
        ConversationTurn(
            role="model",
            content=assistant_summary,
            flow=selected_flow,
        ),
    )

    return OrchestratorResponse(
        session_id=request.session_id,
        selected_flow=selected_flow,
        selected_agent=selected_agent,
        result=result,
        session_history=store.get_history(request.session_id),
    )
