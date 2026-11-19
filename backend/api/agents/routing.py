from typing import Literal

from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .callbacks import guard_untrusted_input_callback
from .config import get_agent_model
from .schemas import ConversationTurn, IntentRouteDecision, OrchestratorRequest
from .session import format_history_context

ORCHESTRATOR_ROUTER_APP_NAME = "sabor_da_terra_intent_router"
ROUTER_OUTPUT_KEY = "orchestrator_route"

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
    "financeiro",
    "financeira",
    "resumo",
    "vendas",
    "pagamentos",
    "pendências",
    "pendencias",
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


def create_default_router_runner(model: str | None = None) -> Runner:
    return Runner(
        app_name=ORCHESTRATOR_ROUTER_APP_NAME,
        agent=create_intent_router_agent(model=model),
        session_service=InMemorySessionService(),
    )


def infer_free_chat_flow(
    request: OrchestratorRequest,
    history: list[ConversationTurn],
) -> Literal["triage", "consultation"]:
    """Heurística de fallback para classificar o fluxo quando o classificador semântico falha."""
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
    router_runner: Runner | None = None,
    *,
    model: str | None = None,
) -> Literal["triage", "consultation"]:
    """Usa o classificador semântico por padrão e recorre à heurística em caso de falha ou saída inválida."""
    try:
        active_runner = (
            router_runner
            if router_runner is not None
            else create_default_router_runner(model=model)
        )
        user_id = f"user-{request.session_id}"
        session = await active_runner.session_service.create_session(
            app_name=active_runner.app_name,
            user_id=user_id,
        )
        history_block = format_history_context(history)
        prompt_parts = [p for p in (history_block, request.message_text) if p]
        message = types.Content(
            role="user",
            parts=[types.Part(text="\n\n".join(prompt_parts))],
        )

        final_text: str | None = None
        async for event in active_runner.run_async(
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

        updated_session = await active_runner.session_service.get_session(
            app_name=active_runner.app_name,
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
    except Exception:  # noqa: BLE001
        return infer_free_chat_flow(request, history)

    return infer_free_chat_flow(request, history)
