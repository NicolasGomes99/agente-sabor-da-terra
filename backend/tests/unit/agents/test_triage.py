from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.models import LlmRequest
from google.genai import types
from pydantic import ValidationError

from api.agents.callbacks import guard_untrusted_input_callback
from api.agents.config import (
    DEFAULT_AGENT_MODEL,
    get_agent_model,
    is_enterprise_enabled,
    to_pernambuco_date,
)
from api.agents.triage import (
    PendingCategory,
    RequestType,
    TriageAnalysis,
    TriageExtractedData,
    TriageInput,
    UrgencyLevel,
    analyze_triage_message,
    build_reference_calendar_context,
    build_triage_instruction,
    classify_urgency,
    create_triage_agent,
    format_triage_prompt,
    triage_agent,
)


class FakeSessionService:
    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}
        self._initial_state = initial_state or {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id="session-test-1",
            app_name=app_name,
            user_id=user_id,
            state=dict(self._initial_state),
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


class FakeRunner:
    def __init__(
        self,
        response_payload: dict[str, Any] | TriageAnalysis,
        *,
        store_in_state: bool = True,
    ) -> None:
        self.app_name = "sabor_da_terra_triage"
        self.session_service = FakeSessionService()
        self._response_payload = response_payload
        self._store_in_state = store_in_state
        self.last_message_text: str | None = None

    async def run_async(
        self,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[SimpleNamespace]:
        _ = user_id
        self.last_message_text = new_message.parts[0].text
        session = self.session_service.sessions[session_id]

        if isinstance(self._response_payload, TriageAnalysis):
            json_text = self._response_payload.model_dump_json()
            state_val: Any = self._response_payload.model_dump()
        else:
            import json

            json_text = json.dumps(self._response_payload, ensure_ascii=False)
            state_val = self._response_payload

        if self._store_in_state:
            session.state["triage_analysis"] = state_val

        event = SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json_text)],
            ),
            is_final_response=lambda: True,
        )
        yield event


def test_get_agent_model_uses_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_AGENT_MODEL", raising=False)
    assert get_agent_model() == DEFAULT_AGENT_MODEL


def test_get_agent_model_reads_configured_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_AGENT_MODEL", " gemini-3.8-pro ")
    assert get_agent_model() == "gemini-3.8-pro"


def test_get_agent_model_rejects_blank_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_AGENT_MODEL", "   ")
    with pytest.raises(RuntimeError, match="GEMINI_AGENT_MODEL must not be blank."):
        get_agent_model()


@pytest.mark.parametrize(
    ("env_name", "env_val", "expected"),
    [
        ("GOOGLE_GENAI_USE_ENTERPRISE", "true", True),
        ("GOOGLE_GENAI_USE_VERTEXAI", "1", True),
        ("GOOGLE_GENAI_USE_ENTERPRISE", "false", False),
    ],
)
def test_is_enterprise_enabled(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_val: str,
    expected: bool,
) -> None:
    monkeypatch.delenv("GOOGLE_GENAI_USE_ENTERPRISE", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setenv(env_name, env_val)
    assert is_enterprise_enabled() is expected


def test_to_pernambuco_date_converts_utc_across_midnight() -> None:
    # 2026-10-29 01:30 UTC == 2026-10-28 22:30 in Pernambuco (America/Recife, UTC-3)
    utc_dt = datetime(2026, 10, 29, 1, 30, tzinfo=UTC)
    assert to_pernambuco_date(utc_dt) == date(2026, 10, 28)
    assert to_pernambuco_date("2026-10-28T09:15:00") == date(2026, 10, 28)
    assert to_pernambuco_date(date(2026, 10, 28)) == date(2026, 10, 28)


def test_build_reference_calendar_context_matches_october_2026_weekdays() -> None:
    calendar_text = build_reference_calendar_context(date(2026, 10, 28), days_ahead=5)
    assert "2026-10-28 (quarta-feira) — dia do recebimento (hoje)" in calendar_text
    assert (
        "2026-10-29 (quinta-feira) — dia seguinte ao recebimento (amanhã)"
        in calendar_text
    )
    assert "2026-10-30 (sexta-feira)" in calendar_text
    assert "2026-10-31 (sábado)" in calendar_text
    assert "2026-11-01 (domingo)" in calendar_text


def test_format_triage_prompt_wraps_message_in_delimiters() -> None:
    payload = TriageInput(
        source_id="PED-2026-003",
        received_at="2026-10-28T11:05:00",
        channel="whatsapp",
        sender="(81) 99234-5678",
        buyer_name="Chef Amanda - Bistrô Sertão Gourmet",
        message_text="preciso urgente pra amanha",
    )
    prompt = format_triage_prompt(payload)
    assert "<metadados_recebimento>" in prompt
    assert "data_recebimento_referencia: 2026-10-28 (quarta-feira)" in prompt
    assert "<calendario_referencia>" in prompt
    assert "<mensagem_recebida>\npreciso urgente pra amanha\n</mensagem_recebida>" in prompt


def test_guard_untrusted_input_callback_blocks_blank_message() -> None:
    empty_request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="   ")])]
    )
    response = guard_untrusted_input_callback(SimpleNamespace(), empty_request)
    assert response is not None
    assert "Mensagem vazia" in response.content.parts[0].text

    valid_request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="Pedido de mel")])]
    )
    assert guard_untrusted_input_callback(SimpleNamespace(), valid_request) is None


@pytest.mark.parametrize(
    ("received", "delivery_start", "declared", "conflict", "expected_level"),
    [
        (date(2026, 10, 28), date(2026, 10, 28), False, False, UrgencyLevel.URGENT),
        (date(2026, 10, 28), date(2026, 10, 29), False, False, UrgencyLevel.URGENT),
        (date(2026, 10, 28), date(2026, 10, 31), False, False, UrgencyLevel.NORMAL),
        (date(2026, 10, 28), date(2026, 11, 4), True, False, UrgencyLevel.URGENT),
        (date(2026, 10, 28), None, False, False, UrgencyLevel.UNDETERMINED),
        (date(2026, 10, 28), date(2026, 11, 1), False, True, UrgencyLevel.UNDETERMINED),
    ],
)
def test_classify_urgency_follows_rf04_rules(
    received: date,
    delivery_start: date | None,
    declared: bool,
    conflict: bool,
    expected_level: UrgencyLevel,
) -> None:
    level, reason = classify_urgency(
        received_date=received,
        delivery_date_start=delivery_start,
        declared_urgency=declared,
        has_date_conflict=conflict,
    )
    assert level == expected_level
    assert len(reason) > 10


def test_triage_extracted_data_rejects_invalid_date_interval() -> None:
    with pytest.raises(
        ValidationError,
        match="delivery_date_end must be greater than or equal to delivery_date_start",
    ):
        TriageExtractedData(
            delivery_date_start="2026-11-08",
            delivery_date_end="2026-11-04",
        )


def test_create_triage_agent_configures_adk_agent() -> None:
    agent = create_triage_agent(model="gemini-3.5-flash")
    assert agent.name == "triage_agent"
    assert agent.output_schema is TriageAnalysis
    assert agent.output_key == "triage_analysis"
    assert triage_agent.name == "triage_agent"
    instruction_text = build_triage_instruction(SimpleNamespace())
    assert "<mensagem_recebida>" in instruction_text
    assert "RF02" in instruction_text
    assert "RF04" in instruction_text


@pytest.mark.asyncio
async def test_analyze_ped_2026_001_detects_date_conflict_and_conditional_item() -> None:
    # PED-2026-001: recebida em 2026-10-28 (quarta), pede "pra essa sexta (01/nov)"
    # e "Se tiver ricota fresca também quero uns 5kg."
    payload = TriageInput(
        source_id="PED-2026-001",
        received_at="2026-10-28T09:15:00",
        channel="email",
        sender="compras@restauranteraizes.com.br",
        buyer_name="Restaurante Raízes",
        message_text=(
            "Bom dia! Preciso pra essa sexta (01/nov): 30kg de queijo coalho, "
            "10kg de manteiga de garrafa, 5kg de mel (aquele silvestre mesmo), "
            "20 maços de coentro e 10 de cebolinha. Se tiver ricota fresca "
            "também quero uns 5kg. Obrigado! Carlos."
        ),
    )

    simulated_model_output = {
        "summary": (
            "Pedido do Restaurante Raízes de laticínios, mel e hortaliças com "
            "item condicional de ricota e conflito na data de entrega."
        ),
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",  # Validator must correct to 'indeterminada' due to date conflict
        "urgency_reason": "Prazo informado para o fim da semana.",
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Restaurante Raízes",
            "buyer_contact": "Carlos (compras@restauranteraizes.com.br)",
            "delivery_date_start": None,
            "delivery_date_end": None,
            "delivery_reference_raw": "essa sexta (01/nov)",
            "has_date_conflict": True,
            "date_conflict_description": (
                "O remetente menciona 'essa sexta (01/nov)', mas a sexta-feira "
                "seguinte a 28/10/2026 é 30/10/2026, enquanto 01/11/2026 é domingo."
            ),
            "items": [
                {
                    "product": "Queijo coalho",
                    "quantity": 30,
                    "quantity_raw": "30kg",
                    "unit": "kg",
                    "conditional": False,
                },
                {
                    "product": "Manteiga de garrafa",
                    "quantity": 10,
                    "quantity_raw": "10kg",
                    "unit": "kg",
                    "conditional": False,
                },
                {
                    "product": "Mel silvestre",
                    "quantity": 5,
                    "quantity_raw": "5kg",
                    "unit": "kg",
                    "conditional": False,
                },
                {
                    "product": "Coentro",
                    "quantity": 20,
                    "quantity_raw": "20 maços",
                    "unit": "maço",
                    "conditional": False,
                },
                {
                    "product": "Cebolinha",
                    "quantity": 10,
                    "quantity_raw": "10 de cebolinha",
                    "unit": "maço",
                    "conditional": False,
                },
                {
                    "product": "Ricota fresca",
                    "quantity": 5,
                    "quantity_raw": "uns 5kg",
                    "unit": "kg",
                    "conditional": True,
                    "condition_text": "se tiver",
                    "ambiguous_or_aggregate": True,
                    "clarification_needed": (
                        "Confirmar se o comprador deseja exatos 5 kg de ricota "
                        "fresca caso haja disponibilidade."
                    ),
                },
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }

    runner = FakeRunner(simulated_model_output)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.request_type == RequestType.ORDER
    assert result.urgency == UrgencyLevel.UNDETERMINED
    assert result.extracted_data.has_date_conflict is True
    assert result.requires_clarification is True

    ricota_item = next(
        item for item in result.extracted_data.items if "ricota" in item.product.lower()
    )
    assert ricota_item.conditional is True
    assert ricota_item.condition_text == "se tiver"

    categories = {p.category for p in result.pending_items}
    assert PendingCategory.DATE_CONFLICT in categories
    assert PendingCategory.AMBIGUOUS_QUANTITY in categories


@pytest.mark.asyncio
async def test_analyze_ped_2026_003_resolves_relative_date_tomorrow_and_urgency() -> None:
    # PED-2026-003: recebida em 28/10/2026, pede "urgente pra amanha" -> 29/10/2026 (US02)
    payload = TriageInput(
        source_id="PED-2026-003",
        received_at="2026-10-28T11:05:00",
        channel="whatsapp",
        sender="(81) 99234-5678",
        buyer_name="Chef Amanda - Bistrô Sertão Gourmet",
        message_text=(
            "oi td bem? to precisando daquele queijo q vcs mandaram da ultima vez, "
            "o mais artesanal sabe? uns 15kg. e tem mel de jandaíra?? quero 3kg. "
            "preciso urgente pra amanha se possivel. manda o pix q eu transfiro agora"
        ),
    )

    simulated_model_output = {
        "summary": (
            "Pedido urgente do Bistrô Sertão Gourmet para entrega em 29/10/2026 "
            "(queijo artesanal a especificar e 3 kg de mel de jandaíra)."
        ),
        "request_type": "pedido",
        "additional_intents": ["Consulta de disponibilidade de mel de jandaíra"],
        "declared_urgency": True,
        "urgency": "urgente",
        "urgency_reason": (
            "Urgência explícita declarada ('preciso urgente') e entrega solicitada "
            "para amanhã (29/10/2026), dia seguinte ao recebimento em 28/10/2026."
        ),
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Chef Amanda - Bistrô Sertão Gourmet",
            "buyer_contact": "(81) 99234-5678",
            "delivery_date_start": "2026-10-29",
            "delivery_reference_raw": "pra amanha",
            "payment_terms": "PIX imediato",
            "items": [
                {
                    "product": "Queijo artesanal (tipo não especificado)",
                    "original_mention": "aquele queijo q vcs mandaram da ultima vez, o mais artesanal",
                    "quantity": 15,
                    "quantity_raw": "uns 15kg",
                    "unit": "kg",
                    "ambiguous_or_aggregate": True,
                    "clarification_needed": (
                        "Confirmar qual tipo de queijo (coalho, manteiga ou ricota) "
                        "e a quantidade exata desejada (informado 'uns 15kg')."
                    ),
                },
                {
                    "product": "Mel de jandaíra",
                    "quantity": 3,
                    "quantity_raw": "3kg",
                    "unit": "kg",
                    "ambiguous_or_aggregate": False,
                },
            ],
        },
        "pending_items": [
            {
                "category": "produto_indefinido",
                "description": "Tipo exato do queijo não foi especificado na mensagem.",
                "question_for_staff": (
                    "Qual foi o queijo entregue anteriormente ao Bistrô Sertão Gourmet "
                    "(queijo coalho ou queijo manteiga) e confirma a quantidade de 15 kg?"
                ),
            }
        ],
        "requires_clarification": True,
    }

    runner = FakeRunner(simulated_model_output)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.request_type == RequestType.ORDER
    assert result.urgency == UrgencyLevel.URGENT
    assert result.extracted_data.delivery_date_start == "2026-10-29"
    assert result.extracted_data.delivery_start_as_date == date(2026, 10, 29)
    assert result.requires_clarification is True


@pytest.mark.asyncio
async def test_analyze_ped_2026_004_preserves_date_interval_and_contract_requirements() -> None:
    # PED-2026-004: intervalo de 04 a 08/11/2026, Contrato nº 045/2026-PNAE, mel orgânico
    payload = TriageInput(
        source_id="PED-2026-004",
        received_at="2026-10-28T14:20:00",
        channel="email",
        sender="licitacoes@educacao.garanhuns.pe.gov.br",
        buyer_name="Prefeitura de Garanhuns - PNAE",
        message_text=(
            "Conforme Contrato nº 045/2026-PNAE, solicitamos a entrega dos itens "
            "para o período de 04 a 08 de novembro de 2026: Banana prata: 200kg; "
            "Mel silvestre (com certificação orgânica): 20kg. Entrega das 7h às 12h."
        ),
    )

    simulated_model_output = {
        "summary": (
            "Pedido institucional do PNAE Garanhuns para entrega entre 04/11/2026 "
            "e 08/11/2026 conforme Contrato nº 045/2026-PNAE."
        ),
        "request_type": "pedido",
        "additional_intents": [],
        "declared_urgency": False,
        "urgency": "normal",
        "urgency_reason": (
            "Primeiro dia do intervalo de entrega (04/11/2026) é posterior ao dia "
            "seguinte ao recebimento (28/10/2026) e não há urgência declarada."
        ),
        "received_date_reference": "2026-10-28",
        "extracted_data": {
            "buyer_name": "Prefeitura de Garanhuns - PNAE",
            "delivery_date_start": "2026-11-04",
            "delivery_date_end": "2026-11-08",
            "delivery_time_window": "das 7h às 12h",
            "contract_reference": "Contrato nº 045/2026-PNAE",
            "items": [
                {"product": "Banana prata", "quantity": 200, "unit": "kg"},
                {
                    "product": "Mel silvestre",
                    "quantity": 20,
                    "unit": "kg",
                    "condition_text": "com certificação orgânica",
                },
            ],
            "requirements": [
                {
                    "description": "Certificação orgânica vigente para o mel silvestre.",
                    "source": "ambos",
                    "contract_reference": "Contrato nº 045/2026-PNAE",
                    "verification_needed": (
                        "Conferir vigência do certificado orgânico e DAP/CAF dos "
                        "produtores durante o intervalo de 04/11/2026 a 08/11/2026."
                    ),
                }
            ],
        },
        "pending_items": [
            {
                "category": "verificacao_de_exigencia_ou_contrato",
                "description": "Exigências do Contrato nº 045/2026-PNAE e certificação orgânica.",
                "question_for_staff": (
                    "Conferir as exigências do Contrato nº 045/2026-PNAE e a "
                    "vigência da certificação orgânica para o mel."
                ),
            }
        ],
        "requires_clarification": True,
    }

    runner = FakeRunner(simulated_model_output)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.urgency == UrgencyLevel.NORMAL
    assert result.extracted_data.delivery_date_start == "2026-11-04"
    assert result.extracted_data.delivery_date_end == "2026-11-08"
    assert result.extracted_data.contract_reference == "Contrato nº 045/2026-PNAE"
    assert len(result.extracted_data.requirements) == 1


@pytest.mark.asyncio
async def test_analyze_ped_2026_009_flags_aggregate_quantities_and_sensitive_requests() -> None:
    # PED-2026-009: cotação semanal com quantidades agregadas ("100kg total", "60kg total")
    # e pedido de documentos e dados pessoais (CPF, endereço, CAF)
    payload = TriageInput(
        source_id="PED-2026-009",
        received_at="2026-10-29T11:45:00",
        channel="email",
        sender="nutricao@hospitalsaofrancisco.com.br",
        buyer_name="Hospital São Francisco",
        message_text=(
            "Solicitamos cotação e disponibilidade para fornecimento semanal:\n"
            "- Frutas variadas (goiaba, banana, manga, maracujá): 100kg total\n"
            "- Hortaliças (alface, couve, espinafre, tomate, cebolinha): 60kg total\n"
            "Favor enviar cópias das certificações, fichas técnicas e dados "
            "cadastrais dos produtores (nome, CPF, endereço e registro no CAF)."
        ),
    )

    simulated_model_output = {
        "summary": (
            "Cotação semanal para o Hospital São Francisco com quantidades "
            "agregadas de frutas e hortaliças e solicitação de documentos e dados cadastrais."
        ),
        "request_type": "consulta",
        "additional_intents": ["Solicitação de documentos e dados cadastrais de produtores"],
        "declared_urgency": False,
        "urgency": "indeterminada",
        "urgency_reason": "Cotação sem data específica de início de entrega e sem urgência declarada.",
        "received_date_reference": "2026-10-29",
        "extracted_data": {
            "buyer_name": "Hospital São Francisco",
            "supply_frequency": "semanal",
            "items": [
                {
                    "product": "Frutas variadas (goiaba, banana, manga, maracujá)",
                    "quantity": None,
                    "quantity_raw": "100kg total",
                    "unit": "kg",
                    "ambiguous_or_aggregate": True,
                    "clarification_needed": (
                        "Especificar a quantidade individual de goiaba, banana, "
                        "manga e maracujá dentro dos 100 kg totais."
                    ),
                },
                {
                    "product": "Hortaliças variadas (alface, couve, espinafre, tomate, cebolinha)",
                    "quantity": None,
                    "quantity_raw": "60kg total",
                    "unit": "kg",
                    "ambiguous_or_aggregate": True,
                    "clarification_needed": (
                        "Especificar a quantidade e unidade individual de cada "
                        "hortaliça dentro dos 60 kg totais."
                    ),
                },
            ],
            "requested_documents_or_sensitive_data": [
                "Cópias das certificações orgânicas",
                "Fichas técnicas dos produtos",
                "Nome, CPF, endereço e registro no CAF dos produtores",
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }

    runner = FakeRunner(simulated_model_output)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.request_type == RequestType.CONSULTATION
    assert result.urgency == UrgencyLevel.UNDETERMINED
    assert result. extracted_data.supply_frequency == "semanal"
    categories = {p.category for p in result.pending_items}
    assert PendingCategory.AMBIGUOUS_QUANTITY in categories
    assert PendingCategory.SENSITIVE_OR_DOCUMENT_REQUEST in categories
    assert result.requires_clarification is True


@pytest.mark.asyncio
async def test_analyze_ped_2026_011_interprets_english_message_in_portuguese() -> None:
    # PED-2026-011: mensagem em inglês, resultado em português (US02 / RF02)
    payload = TriageInput(
        source_id="PED-2026-011",
        received_at="2026-10-30T07:50:00",
        channel="email",
        sender="exporta@tropicalfruits.com.br",
        buyer_name="Tropical Fruits Exportadora",
        message_text=(
            "Dear Sabor da Terra, We are interested in sourcing organic tropical "
            "fruits for export to the European market. We need: Mango: 500kg/month, "
            "Guava: 300kg/month, Passion fruit: 200kg/month. Please provide "
            "producer list with certifications and bank details for international wire transfer."
        ),
    )

    simulated_model_output = {
        "summary": (
            "Consulta de fornecimento mensal de frutas orgânicas para exportação "
            "(manga, goiaba e maracujá) com solicitação de documentos e dados bancários."
        ),
        "request_type": "consulta",
        "additional_intents": [
            "Solicitação de lista de produtores certificados, documentos fitossanitários e dados bancários"
        ],
        "declared_urgency": False,
        "urgency": "indeterminada",
        "urgency_reason": "Consulta comercial sem data de entrega definida e sem urgência declarada.",
        "received_date_reference": "2026-10-30",
        "extracted_data": {
            "buyer_name": "Tropical Fruits Exportadora",
            "supply_frequency": "mensal",
            "items": [
                {
                    "product": "Manga",
                    "original_mention": "Mango: 500kg/month",
                    "quantity": 500,
                    "unit": "kg",
                    "condition_text": "orgânica com certificação brasileira e equivalente internacional",
                },
                {
                    "product": "Goiaba",
                    "original_mention": "Guava: 300kg/month",
                    "quantity": 300,
                    "unit": "kg",
                    "condition_text": "orgânica com certificação brasileira e equivalente internacional",
                },
                {
                    "product": "Maracujá",
                    "original_mention": "Passion fruit: 200kg/month",
                    "quantity": 200,
                    "unit": "kg",
                    "condition_text": "orgânico com certificação brasileira e equivalente internacional",
                },
            ],
            "requested_documents_or_sensitive_data": [
                "Lista completa de produtores com certificações",
                "Documentação de rastreabilidade",
                "Certificados fitossanitários",
                "Dados bancários para transferência internacional",
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }

    runner = FakeRunner(simulated_model_output, store_in_state=False)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.request_type == RequestType.CONSULTATION
    assert [item.product for item in result.extracted_data.items] == [
        "Manga",
        "Goiaba",
        "Maracujá",
    ]
    assert PendingCategory.SENSITIVE_OR_DOCUMENT_REQUEST in {
        p.category for p in result.pending_items
    }


@pytest.mark.asyncio
async def test_analyze_ped_2026_015_preserves_offer_and_additional_registration_intent() -> None:
    # PED-2026-015: oferta de produtor acompanhada de solicitação de cadastro do vizinho (US02)
    payload = TriageInput(
        source_id="PED-2026-015",
        received_at="2026-10-30T16:00:00",
        channel="whatsapp",
        sender="(87) 99745-1098",
        buyer_name="Cícero (Produtor P003)",
        message_text=(
            "Lúcia, to com 200kg de queijo coalho pronto e 30kg de manteiga. "
            "Tem pedido pra mim essa semana? Me avisa até amanhã. E outra coisa: "
            "meu vizinho Sebastião quer se cadastrar na cooperativa, ele produz "
            "doce de leite e queijo de cabra."
        ),
    )

    simulated_model_output = {
        "summary": (
            "Oferta de 200 kg de queijo coalho e 30 kg de manteiga do produtor "
            "Cícero, consulta de pedidos na semana e pedido de cadastro para vizinho."
        ),
        "request_type": "oferta",
        "additional_intents": [
            "Consulta sobre existência de pedidos alocados na semana",
            "Solicitação de cadastro do novo produtor Sebastião (doce de leite e queijo de cabra)",
        ],
        "declared_urgency": False,
        "urgency": "urgente",
        "urgency_reason": "Retorno solicitado até o dia seguinte ao recebimento (31/10/2026).",
        "received_date_reference": "2026-10-30",
        "extracted_data": {
            "buyer_name": "Cícero (Produtor P003)",
            "delivery_date_start": "2026-10-31",
            "items": [
                {"product": "Queijo coalho", "quantity": 200, "unit": "kg"},
                {"product": "Manteiga", "quantity": 30, "unit": "kg"},
            ],
        },
        "pending_items": [],
        "requires_clarification": False,
    }

    runner = FakeRunner(simulated_model_output)
    result = await analyze_triage_message(payload, runner=runner)

    assert result.request_type == RequestType.OFFER
    assert result.urgency == UrgencyLevel.URGENT
    assert len(result.additional_intents) == 2
    assert any("cadastro" in intent.lower() for intent in result.additional_intents)


def test_triage_schema_is_compatible_with_google_genai_transformer() -> None:
    from google.genai._transformers import t_schema

    from api.agents.triage.schemas import TriageExtractedItem

    schema = t_schema(None, TriageAnalysis)
    assert schema is not None

    with pytest.raises(ValidationError, match="quantity must be greater than zero"):
        TriageExtractedItem(product="Queijo coalho", quantity=0)
