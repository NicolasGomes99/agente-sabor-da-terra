from datetime import date, timedelta
from uuid import uuid4

from google.adk import Agent, Runner
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..callbacks import UNTRUSTED_DATA_NOTICE, guard_untrusted_input_callback
from ..config import get_agent_model
from .schemas import TriageAnalysis, TriageInput

PORTUGUESE_WEEKDAYS: tuple[str, ...] = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

TRIAGE_APP_NAME = "sabor_da_terra_triage"
TRIAGE_OUTPUT_KEY = "triage_analysis"

_TRIAGE_SYSTEM_PROMPT = f"""Você é o Agente de Triagem da Cooperativa Agrícola Sabor da Terra.
Sua função é analisar mensagens recebidas pela cooperativa e produzir uma análise estruturada rigorosa em português.

{UNTRUSTED_DATA_NOTICE}

## Regras de Idioma (RF02)
- Analise mensagens escritas em português ou em inglês (incluindo linguagem coloquial, abreviações, erros de digitação e termos implícitos).
- Apresente TODOS os campos da análise (`summary`, `urgency_reason`, nomes de produtos em `items`, `additional_intents`, `requirements`, `pending_items`) obrigatoriamente em português.
- Quando a mensagem estiver em inglês, traduza o nome do produto para o português em `product` e preserve o trecho original em `original_mention`.

## Regras de Datas, Ações e Prazos (RF02, RF04, RF13)
- Interprete datas relativas ("hoje", "amanhã", "essa sexta", "sábado", "próxima semana") sempre a partir da data original de recebimento informada em `<metadados_recebimento>` e na tabela `<calendario_referencia>`, considerando o fuso horário de Pernambuco (`America/Recife`).
- Distinga obrigatoriamente os três tipos de prazo em `extracted_data`:
  1. `entrega` (`delivery_date_start` / `delivery_date_end` e item em `deadlines` com `action = "entrega"`): quando houver solicitação de entrega de produtos. Para intervalos, use o primeiro dia em `delivery_date_start` e o último em `delivery_date_end`.
  2. `resposta` (`response_deadline` e item em `deadlines` com `action = "resposta"`): quando o remetente pedir retorno/resposta até determinada data (ex.: "me avisa até amanhã"). NUNCA grave prazo de resposta em `delivery_date_start` se não houver prazo de entrega.
  3. `disponibilizacao_de_documentos` (`document_availability_date_start` / `document_availability_date_end` e item em `deadlines` com `action = "disponibilizacao_de_documentos"`): quando houver data ou período em que documentos devem estar disponíveis (ex.: inspeção sanitária). Para períodos, considere o primeiro dia em `document_availability_date_start`. NUNCA grave esse prazo em `delivery_date_start`.
- Verifique se o dia da semana citado na mensagem coincide com a data explícita na tabela `<calendario_referencia>`.
- Se a data explícita e o dia da semana entrarem em conflito (por exemplo, o remetente escreve "essa sexta (01/nov)" mas no calendário de referência sexta-feira é outra data e 01/nov cai em outro dia da semana):
  - Marque `has_date_conflict = true` (e `has_conflict = true` no item correspondente em `deadlines`).
  - Explique claramente quais referências entram em conflito em `date_conflict_description`.
  - Deixe a data conflitante como `null` (ou desconsidere-a na classificação) e registre uma pendência com categoria `conflito_de_data` perguntando ao funcionário qual data deve prevalecer.
- Se um prazo informado for anterior à data de recebimento, sinalize a inconsistência e desconsidere essa data no cálculo da urgência por prazo.
- Ao retomar uma conversa com `<historico_sessao_atual>`:
  - Mantenha dados e prazos já esclarecidos que não foram alterados pelo funcionário.
  - Se o funcionário informar que um prazo foi alterado, cancelado ou ficou em aberto, atualize ou deixe como `null` sem restaurar a informação invalidada.

## Regras de Classificação e Intenções (RF04)
- Classifique `request_type` com a intenção principal:
  - `pedido`: solicitação de compra/fornecimento de produtos.
  - `consulta`: cotações de preços/disponibilidade, consultas documentais (certificações, lotes) ou consultas financeiras (saldo, pagamentos, vendas do produtor).
  - `oferta`: produtor informando produção disponível para venda/entrega.
  - `comunicado`: notificações oficiais, avisos de fiscalização/inspeção ou informes institucionais.
  - `nao_identificado`: quando não for possível determinar a intenção.
- Preserve em `additional_intents` quaisquer intenções secundárias presentes na mesma mensagem (ex.: pedido de cotação junto com pedido de envio de documentos, ou oferta de produtos acompanhada de solicitação de cadastro de novo produtor).

## Regras de Urgência (RF04)
- Marque `declared_urgency = true` se a mensagem contiver pedido explícito de urgência (ex.: "urgente", "máxima urgência", "preciso pra hoje sem falta").
- Considere o primeiro prazo válido (não conflitante e maior ou igual à data de recebimento) entre entrega, resposta e disponibilização de documentos:
  - `urgente`: quando `declared_urgency = true` OU quando o primeiro prazo válido (entrega, resposta ou disponibilização de documentos) for para o dia do recebimento ou para o dia seguinte.
  - `normal`: quando o primeiro prazo válido for posterior ao dia seguinte ao recebimento e `declared_urgency = false`.
  - `indeterminada`: quando não houver prazo válido (ausente, conflitante ou anterior ao recebimento) e `declared_urgency = false`.
- Registre em `urgency_basis_action` e `urgency_basis_date` a ação e a data consideradas quando a classificação se basear em prazo, e explique o motivo de forma consistente em `urgency_reason`.

## Regras de Extração de Pedidos, Condições e Alertas (RF03, RF13, RF37)
- Extraia em `items` cada produto mencionado, preservando a unidade informada em `unit` sem converter unidades por conta própria.
- Se um item for pedido sob condição (ex.: "se tiver", "se houver"), marque `conditional = true` e descreva a condição em `condition_text`.
- Se a quantidade for agregada entre múltiplos produtos (ex.: "Frutas variadas (goiaba, banana, manga): 100kg total"), aproximada/ambígua (ex.: "uns 15kg", "umas caixas") ou o produto for indefinido (ex.: "aquele queijo da última vez"):
  - Marque `ambiguous_or_aggregate = true`.
  - Para quantidades agregadas em que não há quantidade individual por produto, deixe `quantity = null` nos itens individuais (ou registre o grupo indicando a quantidade bruta em `quantity_raw`) e explique em `clarification_needed` o que falta confirmar.
  - Registre um item correspondente em `pending_items` com a pergunta específica para o funcionário.
- Aponte em `requirements` as exigências expressas no pedido (ex.: certificação orgânica, laudo sanitário, rastreabilidade, DAP/CAF, nota fiscal) e se a mensagem cita um contrato (indicando `source` e o que o funcionário precisa conferir em `verification_needed`).
- Se o remetente solicitar documentos internos, cópias de certificados, fichas técnicas, dados pessoais (CPF, RG, endereço) ou dados bancários/PIX (RF37), liste cada item solicitado em `requested_documents_or_sensitive_data` e inclua um alerta em `pending_items` com categoria `solicitacao_de_documento_ou_dado_sensivel`.
"""


def build_reference_calendar_context(
    received_date: date,
    days_ahead: int = 14,
) -> str:
    lines: list[str] = []
    for offset in range(days_ahead + 1):
        current = received_date + timedelta(days=offset)
        weekday_name = PORTUGUESE_WEEKDAYS[current.weekday()]
        if offset == 0:
            label = " — dia do recebimento (hoje)"
        elif offset == 1:
            label = " — dia seguinte ao recebimento (amanhã)"
        else:
            label = ""
        lines.append(f"- {current.isoformat()} ({weekday_name}){label}")
    return "\n".join(lines)


def format_triage_prompt(payload: TriageInput) -> str:
    received_date = payload.received_date
    weekday_name = PORTUGUESE_WEEKDAYS[received_date.weekday()]
    calendar_context = build_reference_calendar_context(received_date)

    metadata_lines = [
        f"data_recebimento_referencia: {received_date.isoformat()} ({weekday_name})",
        f"timestamp_original: {payload.received_at}",
    ]
    if payload.source_id:
        metadata_lines.append(f"id_origem: {payload.source_id}")
    if payload.channel:
        metadata_lines.append(f"canal: {payload.channel}")
    if payload.sender:
        metadata_lines.append(f"remetente: {payload.sender}")
    if payload.buyer_name:
        metadata_lines.append(f"comprador_informado: {payload.buyer_name}")

    metadata_block = "\n".join(metadata_lines)
    sections = [
        f"<metadados_recebimento>\n{metadata_block}\n</metadados_recebimento>",
        f"<calendario_referencia>\n{calendar_context}\n</calendario_referencia>",
    ]
    if payload.conversation_history:
        history_block = payload.conversation_history
        if not history_block.startswith("<historico_sessao_atual>"):
            history_block = (
                f"<historico_sessao_atual>\n{history_block}\n</historico_sessao_atual>"
            )
        sections.append(history_block)
    sections.append(
        f"<mensagem_recebida>\n{payload.message_text}\n</mensagem_recebida>"
    )
    return "\n\n".join(sections)


def build_triage_instruction(context: ReadonlyContext) -> str:
    _ = context
    return _TRIAGE_SYSTEM_PROMPT


def create_triage_agent(model: str | None = None) -> Agent:
    return Agent(
        name="triage_agent",
        model=model or get_agent_model(),
        description=(
            "Analisa mensagens recebidas na triagem (em português ou inglês), "
            "classificando tipo e urgência e extraindo comprador, itens, prazos, "
            "condições e pendências em português."
        ),
        instruction=build_triage_instruction,
        output_schema=TriageAnalysis,
        output_key=TRIAGE_OUTPUT_KEY,
        before_model_callback=guard_untrusted_input_callback,
    )


triage_agent = create_triage_agent()
root_agent = triage_agent


async def analyze_triage_message(
    payload: TriageInput,
    *,
    runner: Runner | None = None,
    model: str | None = None,
) -> TriageAnalysis:
    active_runner = runner
    if active_runner is None:
        agent = create_triage_agent(model=model) if model else triage_agent
        active_runner = Runner(
            app_name=TRIAGE_APP_NAME,
            agent=agent,
            session_service=InMemorySessionService(),
        )

    user_id = "triage-worker"
    session = await active_runner.session_service.create_session(
        app_name=active_runner.app_name,
        user_id=user_id,
    )

    prompt_text = format_triage_prompt(payload)
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
    if updated_session and TRIAGE_OUTPUT_KEY in updated_session.state:
        state_value = updated_session.state[TRIAGE_OUTPUT_KEY]
        if isinstance(state_value, TriageAnalysis):
            analysis = state_value
        elif isinstance(state_value, dict):
            state_data = {
                **state_value,
                "received_date_reference": payload.received_date.isoformat(),
            }
            analysis = TriageAnalysis.model_validate(state_data)
        elif isinstance(state_value, str):
            analysis = TriageAnalysis.model_validate_json(state_value)
        else:
            raise RuntimeError(
                f"Unexpected triage output type in session state: {type(state_value)!r}"
            )
    elif final_text:
        analysis = TriageAnalysis.model_validate_json(final_text)
    else:
        raise RuntimeError(
            f"Triage agent finished without producing a response (run={uuid4()})."
        )

    if analysis.received_date != payload.received_date:
        revalidated = analysis.model_dump()
        revalidated["received_date_reference"] = payload.received_date.isoformat()
        analysis = TriageAnalysis.model_validate(revalidated)

    return analysis.model_copy(update={"document_enrichment": None})
