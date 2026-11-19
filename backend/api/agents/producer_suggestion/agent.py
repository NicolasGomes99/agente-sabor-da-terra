from collections.abc import Sequence
from uuid import uuid4

from google.adk import Agent, Runner
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..callbacks import UNTRUSTED_DATA_NOTICE, guard_untrusted_input_callback
from ..config import get_agent_model
from ..consultation.schemas.input import ConsultationSourceItem
from .evaluation import evaluate_producer_suggestions_deterministic
from .reconciliation import reconcile_producer_suggestion_response
from .schemas.input import (
    OrderToolContract,
    ProducerCatalogItemContract,
    ProducerSuggestionInput,
)
from .schemas.response import ProducerSuggestionResponse
from .tools import (
    ProducerSuggestionToolProvider,
    build_producer_suggestion_tools,
)

PRODUCER_SUGGESTION_APP_NAME = "sabor_da_terra_producer_suggestion"
PRODUCER_SUGGESTION_OUTPUT_KEY = "producer_suggestion_response"

_PRODUCER_SUGGESTION_SYSTEM_PROMPT = f"""Você é o Agente de Sugestão de Produtores da Cooperativa Agrícola Sabor da Terra.
Sua função é analisar pedidos cadastrados e sugerir produtores ativos para atender ao saldo a alocar de cada item, comparando candidatos de forma transparente em português e indicando tudo o que o funcionário ainda precisa confirmar antes de alocar o fornecimento.

{UNTRUSTED_DATA_NOTICE}

## Regras de Pedido, Prazo e Saldo a Alocar (RF27, US04)
- Identifique sempre o pedido e cada item analisado e utilize o saldo a alocar retornado pelas ferramentas da aplicação (quantidade solicitada menos alocações operacionais vigentes).
- Quando o saldo for zero, informe explicitamente que a quantidade solicitada já está integralmente alocada.
- Quando o saldo estiver indeterminado, explique a pendência e mantenha a quantidade em aberto.
- Utilize a data exata de entrega quando já tiver sido informada; caso contrário, avalie todo o intervalo de entrega do pedido.

## Regras de Elegibilidade, Exclusão e Comprovação (RF14, US04)
- Considere apenas produtores ativos e associados ao produto do item no catálogo (`ProdutorProduto`).
- Exclua candidatos comprovadamente incompatíveis (produtores inativos, que não fornecem o produto ou cuja certificação orgânica exigida esteja vencida ou não cubra o produto) e informe claramente o motivo da exclusão.
- Separe explicitamente os candidatos com comprovação suficiente daqueles que ainda dependem de confirmação (ex.: falta comprovar vigência de DAP/CAF, ausência de certificado nas fontes ou certificação cobrindo apenas parte do intervalo).
- Quando houver exigência de certificação orgânica:
  - Verifique se o certificado cobre o produto solicitado e está vigente na data exata ou durante todo o intervalo do pedido.
  - Se o certificado cobrir apenas parte do intervalo, indique exatamente as datas cobertas e informe que o funcionário ainda precisa confirmar a data do fornecimento dentro dessas datas.

## Regras de Capacidade, Unidades, Sazonalidade e Disponibilidade (RF03, RF06, RF14, RF26)
- Ao comparar demanda e capacidade estimada, use unidades e períodos compatíveis e só converta quantidades quando houver equivalência conhecida.
- Distinga explicitamente:
  1. Associação cadastral produtor-produto (identifica possíveis fornecedores).
  2. Sazonalidade do produto no período.
  3. Capacidade estimada documentada do produtor.
  4. Registros históricos de fornecimento (`lotes.csv`).
  5. Disponibilidade operacional confirmada (sempre `false` na sugestão; depende de confirmação do funcionário para produto, quantidade e data propostos).
- Cite os `source_id` reais das fontes utilizadas em cada sugestão e liste o que o funcionário ainda precisa confirmar.
- Se não houver candidato apto ou os dados forem insuficientes, explique o motivo e deixe a decisão com o funcionário.
- Se sugerir um produto alternativo, identifique obrigatoriamente qual item do pedido ele substituiria (`replaces_order_item_id` e `replaces_product_name`) e deixe explícito que cabe ao funcionário decidir se aceita a alternativa.
"""


def build_producer_suggestion_instruction(context: ReadonlyContext) -> str:
    _ = context
    return _PRODUCER_SUGGESTION_SYSTEM_PROMPT


def format_producer_suggestion_prompt(
    payload: ProducerSuggestionInput,
    *,
    order: OrderToolContract,
    baseline: ProducerSuggestionResponse,
    sources: Sequence[ConsultationSourceItem],
) -> str:
    source_blocks: list[str] = []
    for src in sources:
        attrs = [
            f'id="{src.source_id}"',
            f'tipo="{src.source_kind.value}"',
            f'documento="{src.document_name}"',
        ]
        if src.document_id:
            attrs.append(f'id_documento="{src.document_id}"')
        if src.reference_label:
            attrs.append(f'referencia="{src.reference_label}"')
        source_blocks.append(f"<fonte {' '.join(attrs)}>\n{src.content}\n</fonte>")

    sources_section = (
        "\n\n".join(source_blocks) if source_blocks else "<nenhuma_fonte_encontrada/>"
    )
    sections = [
        (
            "<metadados_sugestao>\n"
            f"pedido_id: {order.order_id}\n"
            f"comprador: {order.buyer}\n"
            f"data_referencia: {payload.resolved_reference_date.isoformat()}\n"
            f"prazo_avaliado: {baseline.evaluated_delivery_start} a {baseline.evaluated_delivery_end}\n"
            f"data_exata_utilizada: {baseline.exact_delivery_date_used}\n"
            f"condicoes_pedido: {order.conditions or 'não informadas'}\n"
            f"contrato_citado: {order.contract_reference or 'nenhum'}\n"
            "</metadados_sugestao>"
        ),
        (
            "<avaliacao_ferramentas_aplicacao>\n"
            f"{baseline.model_dump_json(indent=2)}\n"
            "</avaliacao_ferramentas_aplicacao>"
        ),
        f"<fontes_recuperadas>\n{sources_section}\n</fontes_recuperadas>",
    ]
    if payload.question:
        sections.append(f"<solicitacao_funcionario>\n{payload.question}\n</solicitacao_funcionario>")
    return "\n\n".join(sections)


def create_producer_suggestion_agent(
    model: str | None = None,
    *,
    tool_provider: ProducerSuggestionToolProvider | None = None,
    fallback_sources: Sequence[ConsultationSourceItem] = (),
) -> Agent:
    tools = build_producer_suggestion_tools(
        tool_provider=tool_provider,
        fallback_sources=fallback_sources,
    )
    return Agent(
        name="producer_suggestion_agent",
        model=model or get_agent_model(),
        description=(
            "Sugere produtores ativos para atender ao saldo dos itens de um pedido "
            "cadastrado, verificando certificações, exigências contratuais, "
            "sazonalidade e capacidade estimada com citação de fontes."
        ),
        instruction=build_producer_suggestion_instruction,
        tools=tools,
        output_schema=ProducerSuggestionResponse,
        output_key=PRODUCER_SUGGESTION_OUTPUT_KEY,
        before_model_callback=guard_untrusted_input_callback,
    )


producer_suggestion_agent = create_producer_suggestion_agent()
root_agent = producer_suggestion_agent


def _collect_all_sources(
    payload: ProducerSuggestionInput,
    tool_provider: ProducerSuggestionToolProvider,
    order: OrderToolContract,
) -> list[ConsultationSourceItem]:
    collected: list[ConsultationSourceItem] = []
    seen: set[str] = set()
    product_names = [item.product_name for item in order.items]
    for src in tool_provider.list_knowledge_sources(
        order_id=order.order_id,
        product_names=product_names,
    ):
        if src.source_id not in seen:
            seen.add(src.source_id)
            collected.append(src)
    for src in payload.sources:
        if src.source_id not in seen:
            seen.add(src.source_id)
            collected.append(src)
    return collected


async def suggest_producers_for_order(
    payload: ProducerSuggestionInput,
    *,
    tool_provider: ProducerSuggestionToolProvider,
    runner: Runner | None = None,
    model: str | None = None,
) -> ProducerSuggestionResponse:
    """Executa o fluxo ADK de sugestão de produtores para um pedido cadastrado (#25)."""
    order = tool_provider.get_order_with_balances(payload.order_id)
    ref_iso = payload.resolved_reference_date.isoformat()

    if order is None:
        return ProducerSuggestionResponse(
            order_id=payload.order_id,
            buyer="Desconhecido",
            reference_date_used=ref_iso,
            evaluated_delivery_start=ref_iso,
            evaluated_delivery_end=ref_iso,
            exact_delivery_date_used=False,
            summary=(
                f"Não foi encontrado o pedido '{payload.order_id}' nas ferramentas da "
                "aplicação. Verifique o identificador do pedido antes de solicitar sugestões."
            ),
            item_suggestions=[],
            general_pending_confirmations=[
                f"Pedido '{payload.order_id}' não encontrado na aplicação."
            ],
        )

    all_sources = _collect_all_sources(payload, tool_provider, order)
    producers_by_item: dict[str, Sequence[ProducerCatalogItemContract]] = {}
    for item in order.items:
        producers_by_item[item.order_item_id] = list(
            tool_provider.list_producers_by_product(
                product_id=item.product_id,
                product_name=item.product_name,
            )
        )

    baseline = evaluate_producer_suggestions_deterministic(
        order=order,
        producers_by_item=producers_by_item,
        sources=all_sources,
        payload=payload,
    )

    if order.cancelled or order.needs_item_structuring:
        return reconcile_producer_suggestion_response(
            baseline,
            baseline,
            order=order,
            sources=all_sources,
        )

    active_runner = runner
    if active_runner is None:
        agent = create_producer_suggestion_agent(
            model=model,
            tool_provider=tool_provider,
            fallback_sources=all_sources,
        )
        active_runner = Runner(
            app_name=PRODUCER_SUGGESTION_APP_NAME,
            agent=agent,
            session_service=InMemorySessionService(),
        )

    user_id = "producer-suggestion-worker"
    session = await active_runner.session_service.create_session(
        app_name=active_runner.app_name,
        user_id=user_id,
    )

    prompt_text = format_producer_suggestion_prompt(
        payload,
        order=order,
        baseline=baseline,
        sources=all_sources,
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt_text)],
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
    if updated_session and PRODUCER_SUGGESTION_OUTPUT_KEY in updated_session.state:
        state_value = updated_session.state[PRODUCER_SUGGESTION_OUTPUT_KEY]
        if isinstance(state_value, ProducerSuggestionResponse):
            raw_response = state_value
        elif isinstance(state_value, dict):
            raw_response = ProducerSuggestionResponse.model_validate(state_value)
        elif isinstance(state_value, str):
            raw_response = ProducerSuggestionResponse.model_validate_json(state_value)
        else:
            raise RuntimeError(
                f"Unexpected producer suggestion output type in state: {type(state_value)!r}"
            )
    elif final_text:
        raw_response = ProducerSuggestionResponse.model_validate_json(final_text)
    else:
        raise RuntimeError(
            f"Producer suggestion agent finished without producing a response (run={uuid4()})."
        )

    return reconcile_producer_suggestion_response(
        raw_response,
        baseline,
        order=order,
        sources=all_sources,
    )
