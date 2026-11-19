import json
from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from api.agents import (
    ROUTER_OUTPUT_KEY,
    OrchestratorFlow,
    OrchestratorRequest,
    orchestrate_request,
)
from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    FINANCIAL_TOOL_NAME,
    ConsultationInput,
    ConsultationResponse,
    ConsultationSourceItem,
    InMemoryFinancialRecordsProvider,
    SourceKind,
    answer_document_consultation,
    answer_producer_financial_summary,
    build_financial_summary_tool,
    calculate_producer_financial_summary,
    create_consultation_agent,
)


class FakeFinancialSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"session-fin-{len(self.sessions) + 1}",
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


class FakeFinancialConsultationRunner:
    def __init__(
        self,
        response_payload: dict[str, Any],
        *,
        state_key: str = CONSULTATION_OUTPUT_KEY,
        tool_function_response: dict[str, Any] | None = None,
    ) -> None:
        self.app_name = "sabor_da_terra_consultation"
        self.session_service = FakeFinancialSessionService()
        self._response_payload = response_payload
        self._state_key = state_key
        self._tool_function_response = tool_function_response
        self.last_prompt_text: str | None = None

    async def run_async(
        self,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[SimpleNamespace]:
        _ = user_id
        self.last_prompt_text = new_message.parts[0].text
        session = self.session_service.sessions[session_id]

        if self._tool_function_response is not None:
            yield SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            function_response=SimpleNamespace(
                                name=FINANCIAL_TOOL_NAME,
                                response=self._tool_function_response,
                            )
                        )
                    ]
                ),
                is_final_response=lambda: False,
            )

        session.state[self._state_key] = self._response_payload
        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=json.dumps(self._response_payload, ensure_ascii=False)
                    )
                ],
            ),
            is_final_response=lambda: True,
        )


def _make_financial_chunk_source(
    source_id: str,
    fields: dict[str, str],
    *,
    document_id: str = "doc-financeiro-csv",
    document_name: str = "financeiro.csv",
) -> ConsultationSourceItem:
    content = "; ".join(f"{k}={v}" for k, v in fields.items())
    return ConsultationSourceItem(
        source_id=source_id,
        source_kind=SourceKind.FINANCIAL_RECORD,
        document_id=document_id,
        document_name=document_name,
        reference_label=fields["id_transacao"],
        record_id=fields["id_transacao"],
        record_fields=fields,
        content=content,
    )


def _sample_rag_financial_sources() -> list[ConsultationSourceItem]:
    rows = [
        (
            "chunk-fin-001",
            {
                "id_transacao": "FIN-2026-001",
                "data": "2026-09-02",
                "produtor_id": "P001",
                "produtor_nome": "Maria das Graças Silva Ferreira",
                "comprador": "Mercado Bom Preço",
                "tipo": "venda",
                "produto": "goiaba paluma",
                "quantidade_kg": "120",
                "valor_unitario": "4.50",
                "valor_total": "540.00",
                "forma_pagamento": "boleto 30 dias",
                "status_pagamento": "pago",
                "data_vencimento": "2026-10-02",
                "data_pagamento": "2026-10-01",
            },
        ),
        (
            "chunk-fin-002",
            {
                "id_transacao": "FIN-2026-002",
                "data": "2026-09-02",
                "produtor_id": "P001",
                "produtor_nome": "Maria das Graças Silva Ferreira",
                "comprador": "Mercado Bom Preço",
                "tipo": "venda",
                "produto": "manga tommy",
                "quantidade_kg": "80",
                "valor_unitario": "5.00",
                "valor_total": "400.00",
                "forma_pagamento": "boleto 30 dias",
                "status_pagamento": "pago",
                "data_vencimento": "2026-10-02",
                "data_pagamento": "2026-10-01",
            },
        ),
        (
            "chunk-fin-003",
            {
                "id_transacao": "FIN-2026-003",
                "data": "2026-09-05",
                "produtor_id": "P003",
                "produtor_nome": "Cícero Romão de Almeida",
                "comprador": "Restaurante Raízes",
                "tipo": "venda",
                "produto": "queijo coalho",
                "quantidade_kg": "45",
                "valor_unitario": "32.00",
                "valor_total": "1440.00",
                "forma_pagamento": "pix",
                "status_pagamento": "pago",
                "data_vencimento": "2026-09-05",
                "data_pagamento": "2026-09-05",
            },
        ),
        (
            "chunk-fin-006",
            {
                "id_transacao": "FIN-2026-006",
                "data": "2026-09-08",
                "produtor_id": "P004",
                "produtor_nome": "Ana Lúcia Bezerra da Costa",
                "comprador": "Prefeitura de Garanhuns - PNAE",
                "tipo": "venda",
                "produto": "alface",
                "quantidade_kg": "300",
                "valor_unitario": "2.50",
                "valor_total": "750.00",
                "forma_pagamento": "empenho 45 dias",
                "status_pagamento": "pendente",
                "data_vencimento": "2026-10-23",
                "data_pagamento": "",
            },
        ),
        (
            "chunk-fin-007",
            {
                "id_transacao": "FIN-2026-007",
                "data": "2026-09-08",
                "produtor_id": "P004",
                "produtor_nome": "Ana Lúcia Bezerra da Costa",
                "comprador": "Prefeitura de Garanhuns - PNAE",
                "tipo": "venda",
                "produto": "coentro",
                "quantidade_kg": "150",
                "valor_unitario": "1.80",
                "valor_total": "270.00",
                "forma_pagamento": "empenho 45 dias",
                "status_pagamento": "pendente",
                "data_vencimento": "2026-10-23",
                "data_pagamento": "",
            },
        ),
        (
            "chunk-fin-015",
            {
                "id_transacao": "FIN-2026-015",
                "data": "2026-09-20",
                "produtor_id": "P001",
                "produtor_nome": "Maria das Graças Silva Ferreira",
                "comprador": "Restaurante Raízes",
                "tipo": "venda",
                "produto": "goiaba paluma",
                "quantidade_kg": "30",
                "valor_unitario": "5.00",
                "valor_total": "150.00",
                "forma_pagamento": "pix",
                "status_pagamento": "pago",
                "data_vencimento": "2026-09-20",
                "data_pagamento": "2026-09-20",
            },
        ),
    ]
    return [_make_financial_chunk_source(sid, fields) for sid, fields in rows]


def test_consultation_agent_registers_financial_calculation_tool() -> None:
    provider = InMemoryFinancialRecordsProvider(_sample_rag_financial_sources())
    agent = create_consultation_agent(
        model="gemini-3.8-flash",
        financial_records_provider=provider,
    )
    assert len(agent.tools) == 1
    tool_fn = build_financial_summary_tool(financial_records_provider=provider)
    tool_output = tool_fn("P004", "2026-09-01", "2026-09-30", "2026-09-30")
    assert tool_output["producer_id"] == "P004"
    assert tool_output["sales_in_period"]["formatted_total"] == "R$ 1.020,00"
    assert tool_output["sales_in_period"]["transaction_ids"] == [
        "FIN-2026-006",
        "FIN-2026-007",
    ]


@pytest.mark.asyncio
async def test_p004_september_2026_summary_presents_1020_sales_and_upcoming_due_2026_10_23() -> None:
    # Critérios 1, 4 e 5 da #40: resumo de P004 para setembro/2026 com referência em 30/09/2026
    # apresenta R$ 1.020,00 em vendas e R$ 1.020,00 a vencer em 23/10/2026, citando
    # FIN-2026-006 e FIN-2026-007 de financeiro.csv e excluindo registros de outros produtores
    provider = InMemoryFinancialRecordsProvider(_sample_rag_financial_sources())

    simulated_model_output = {
        "answer": (
            "No resumo de Ana Lúcia Bezerra da Costa (P004) para setembro de 2026, "
            "com data de referência em 30/09/2026:\n"
            "- Vendas: R$ 1.020,00 (FIN-2026-006 e FIN-2026-007 de financeiro.csv).\n"
            "- Pagamentos registrados: não foram encontrados registros de pagamento em setembro na base.\n"
            "- Pendências a vencer: R$ 1.020,00 a vencer em 23/10/2026 "
            "(FIN-2026-006 e FIN-2026-007 de financeiro.csv)."
        ),
        "reference_date_used": "2026-09-30",
        "source_ids": ["chunk-fin-006", "chunk-fin-007"],
        "cited_sources": [],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }
    runner = FakeFinancialConsultationRunner(simulated_model_output)

    response, calc = await answer_producer_financial_summary(
        "P004",
        period="2026-09",
        reference_date="2026-09-30",
        financial_records_provider=provider,
        runner=runner,
    )

    assert calc.sales_in_period.total_amount == Decimal("1020.00")
    assert calc.sales_in_period.formatted_total == "R$ 1.020,00"
    assert calc.sales_in_period.transaction_ids == ["FIN-2026-006", "FIN-2026-007"]
    assert calc.registered_payments_in_period.has_records is False
    assert calc.pending_upcoming.total_amount == Decimal("1020.00")
    assert calc.pending_upcoming.formatted_total == "R$ 1.020,00"
    assert calc.pending_upcoming.due_dates == ["2026-10-23"]
    assert calc.pending_upcoming.transaction_ids == ["FIN-2026-006", "FIN-2026-007"]
    assert calc.pending_overdue.has_records is False

    # Exclui P001 e P003
    assert "FIN-2026-001" not in calc.all_transaction_ids
    assert "FIN-2026-003" not in calc.all_transaction_ids

    assert isinstance(response, ConsultationResponse)
    assert "R$ 1.020,00" in response.answer
    assert "23/10/2026" in response.answer
    assert "FIN-2026-006" in response.answer
    assert "FIN-2026-007" in response.answer
    assert "financeiro.csv" in response.answer
    assert response.source_ids == ["chunk-fin-006", "chunk-fin-007"]
    assert [c.reference_label for c in response.cited_sources] == [
        "FIN-2026-006",
        "FIN-2026-007",
    ]
    assert all(c.document_name == "financeiro.csv" for c in response.cited_sources)


@pytest.mark.asyncio
async def test_p001_september_and_october_2026_sales_payments_and_pending_transition() -> None:
    # Critérios 2 e 4 da #40: para P001, setembro tem R$ 1.090,00 em vendas (FIN-001, FIN-002, FIN-015),
    # R$ 150,00 em pagamentos registrados no mesmo mês (FIN-015), e R$ 940,00 (FIN-001, FIN-002)
    # aparecem a vencer na referência de 30/09/2026 e entram nos pagamentos registrados de outubro
    provider = InMemoryFinancialRecordsProvider(_sample_rag_financial_sources())

    sept_calc = calculate_producer_financial_summary(
        "P001",
        period_start="2026-09-01",
        period_end="2026-09-30",
        reference_date="2026-09-30",
        financial_records_provider=provider,
    )
    assert sept_calc.sales_in_period.formatted_total == "R$ 1.090,00"
    assert sept_calc.sales_in_period.transaction_ids == [
        "FIN-2026-001",
        "FIN-2026-002",
        "FIN-2026-015",
    ]
    assert sept_calc.registered_payments_in_period.formatted_total == "R$ 150,00"
    assert sept_calc.registered_payments_in_period.transaction_ids == ["FIN-2026-015"]
    assert sept_calc.pending_upcoming.formatted_total == "R$ 940,00"
    assert sept_calc.pending_upcoming.transaction_ids == [
        "FIN-2026-001",
        "FIN-2026-002",
    ]
    assert sept_calc.pending_upcoming.due_dates == ["2026-10-02"]
    assert sept_calc.pending_overdue.has_records is False

    # Em outubro/2026 (referência 31/10/2026), os R$ 940,00 de FIN-2026-001 e FIN-2026-002
    # (pagos em 01/10/2026) entram nos pagamentos registrados de outubro e saem das pendências
    oct_calc = calculate_producer_financial_summary(
        "P001",
        period_start="2026-10-01",
        period_end="2026-10-31",
        reference_date="2026-10-31",
        financial_records_provider=provider,
    )
    assert oct_calc.sales_in_period.has_records is False
    assert oct_calc.registered_payments_in_period.formatted_total == "R$ 940,00"
    assert oct_calc.registered_payments_in_period.transaction_ids == [
        "FIN-2026-001",
        "FIN-2026-002",
    ]
    assert oct_calc.pending_total.has_records is False


@pytest.mark.asyncio
async def test_reconciliation_rejects_swapped_financial_categories_and_hallucinated_amounts() -> None:
    # Revisão PR #47 item 2: mesmo que o modelo inclua todos os valores e IDs corretos no texto,
    # mas troque os valores entre Vendas e Pagamentos registrados (ou adicione valores indevidos),
    # a resposta final deve preservar estritamente cada cálculo, valor e transação (RF08 / RNF04).
    provider = InMemoryFinancialRecordsProvider(_sample_rag_financial_sources())

    swapped_model_output = {
        "answer": (
            "Resumo financeiro de Maria das Graças Silva Ferreira (P001) em 30/09/2026:\n"
            "- Vendas no período: R$ 150,00 (FIN-2026-001, FIN-2026-002 em financeiro.csv).\n"
            "- Pagamentos registrados: R$ 1.090,00 (FIN-2026-015 em financeiro.csv).\n"
            "- Pendências a vencer em 02/10/2026: R$ 940,00 (FIN-2026-015).\n"
            "- Bônus adicional inventado: R$ 9.999,00."
        ),
        "reference_date_used": "2026-09-30",
        "source_ids": ["chunk-fin-001", "chunk-fin-003"],
        "cited_sources": [
            {
                "source_id": "chunk-fin-003",
                "document_name": "financeiro.csv",
                "reference_label": "FIN-2026-003",
            }
        ],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }
    runner = FakeFinancialConsultationRunner(swapped_model_output)

    response, _ = await answer_producer_financial_summary(
        "P001",
        period_start="2026-09-01",
        period_end="2026-09-30",
        reference_date="2026-09-30",
        financial_records_provider=provider,
        runner=runner,
    )

    lines = response.answer.splitlines()
    sales_line = next(line for line in lines if line.startswith("- Vendas no período:"))
    payments_line = next(
        line for line in lines if line.startswith("- Pagamentos registrados no período")
    )
    upcoming_line = next(line for line in lines if line.startswith("- Pendências a vencer"))

    # Cada categoria está associada exclusivamente ao seu valor e às suas transações
    assert "R$ 1.090,00" in sales_line
    assert "R$ 150,00" not in sales_line
    assert "FIN-2026-001" in sales_line
    assert "FIN-2026-002" in sales_line
    assert "FIN-2026-015" in sales_line

    assert "R$ 150,00" in payments_line
    assert "R$ 1.090,00" not in payments_line
    assert "FIN-2026-015" in payments_line
    assert "FIN-2026-001" not in payments_line
    assert "FIN-2026-002" not in payments_line
    assert "repasse bancário" in payments_line.lower()

    assert "R$ 940,00" in upcoming_line
    assert "02/10/2026" in upcoming_line
    assert "FIN-2026-001" in upcoming_line
    assert "FIN-2026-002" in upcoming_line
    assert "FIN-2026-015" not in upcoming_line

    # Valor inventado e fonte de outro produtor (P003) foram rejeitados
    assert "R$ 9.999,00" not in response.answer
    assert "chunk-fin-003" not in response.source_ids
    assert response.source_ids == ["chunk-fin-001", "chunk-fin-002", "chunk-fin-015"]


@pytest.mark.asyncio
async def test_orchestrate_request_runs_financial_calculation_and_reconciles_values_and_sources() -> None:
    # Revisão PR #47 itens 1 e 3: consulta financeira pelo fluxo oficial orchestrate_request()
    # sem preencher producer_id/period manualmente e com `sources` limitado a 1 trecho (busca top-k),
    # usando o provedor exaustivo de financeiro.csv para recuperar todos os registros elegíveis.
    all_records = _sample_rag_financial_sources()
    provider = InMemoryFinancialRecordsProvider(all_records)
    # Simula busca semântica limitada que trouxe apenas 1 das 3 transações da P001
    truncated_semantic_sources = [all_records[0]]

    router_runner = FakeFinancialConsultationRunner(
        {"target_flow": "consultation", "reason": "Consulta financeira por produtor."},
        state_key=ROUTER_OUTPUT_KEY,
    )
    consultation_runner = FakeFinancialConsultationRunner(
        {
            "answer": "Resposta incompleta do modelo: vendas R$ 540,00.",
            "reference_date_used": "2026-09-30",
            "source_ids": ["chunk-fin-001"],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        }
    )

    orch_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-p001",
            flow=OrchestratorFlow.AUTO,
            received_at="2026-09-30",
            message_text="Gere o resumo financeiro da produtora P001 para setembro de 2026.",
            sources=truncated_semantic_sources,
        ),
        router_runner=router_runner,
        consultation_runner=consultation_runner,
        financial_records_provider=provider,
    )

    assert orch_resp.selected_flow == "consultation"
    assert orch_resp.selected_agent == "consultation_agent"
    assert isinstance(orch_resp.result, ConsultationResponse)
    # Todos os 3 registros elegíveis de P001 foram incluídos (mesmo com sources truncado em 1!)
    assert "R$ 1.090,00" in orch_resp.result.answer
    assert "R$ 150,00" in orch_resp.result.answer
    assert "R$ 940,00" in orch_resp.result.answer
    assert orch_resp.result.source_ids == [
        "chunk-fin-001",
        "chunk-fin-002",
        "chunk-fin-015",
    ]
    assert [c.reference_label for c in orch_resp.result.cited_sources] == [
        "FIN-2026-001",
        "FIN-2026-002",
        "FIN-2026-015",
    ]
    assert all(c.document_name == "financeiro.csv" for c in orch_resp.result.cited_sources)

    # Também valida captura direta de chamada de ferramenta ADK (function_response) via orchestrate_request()
    # quando a pergunta não explicita o código do produtor no texto atual
    tool_fn = build_financial_summary_tool(financial_records_provider=provider)
    tool_payload = tool_fn("P004", "2026-09-01", "2026-09-30", "2026-09-30")
    tool_capturing_runner = FakeFinancialConsultationRunner(
        {
            "answer": "Modelo trocou o valor para R$ 10,00.",
            "reference_date_used": "2026-09-30",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
        tool_function_response=tool_payload,
    )

    orch_tool_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-tool-capture",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-09-30",
            message_text="Quanto essa produtora tem a receber em setembro de 2026?",
            sources=[],
        ),
        consultation_runner=tool_capturing_runner,
        financial_records_provider=provider,
    )
    assert isinstance(orch_tool_resp.result, ConsultationResponse)
    assert "R$ 1.020,00" in orch_tool_resp.result.answer
    assert "R$ 10,00" not in orch_tool_resp.result.answer
    assert orch_tool_resp.result.source_ids == ["chunk-fin-006", "chunk-fin-007"]
    assert [c.reference_label for c in orch_tool_resp.result.cited_sources] == [
        "FIN-2026-006",
        "FIN-2026-007",
    ]


@pytest.mark.asyncio
async def test_financial_calculation_blocks_partial_semantic_sources_without_exhaustive_contract() -> None:
    # Revisão PR #47 item 3: sem provedor/coleção exaustiva de financeiro.csv, a ferramenta
    # não pode calcular totais parciais sobre `sources` de busca semântica como se fossem completos.
    partial_sources = [_sample_rag_financial_sources()[0]]

    with pytest.raises(ValueError, match="exhaustive financial_records_provider"):
        calculate_producer_financial_summary(
            "P001",
            period="2026-09",
            reference_date="2026-09-30",
        )

    orch_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-no-exhaustive",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-09-30",
            message_text="Qual o resumo financeiro da produtora P001 em setembro de 2026?",
            sources=partial_sources,
        ),
    )
    assert isinstance(orch_resp.result, ConsultationResponse)
    assert orch_resp.result.has_sufficient_data is False
    assert orch_resp.result.source_ids == []
    assert "R$ 540,00" not in orch_resp.result.answer
    assert "exaustiva" in orch_resp.result.answer.lower()
    assert any(g.kind == "lacuna" for g in orch_resp.result.gaps_and_divergences)


def test_prior_period_unpaid_sales_are_included_in_pending_and_classified_as_overdue_or_upcoming() -> None:
    # Critério 3 da #40: venda de período anterior (agosto/2026) ainda sem pagamento na
    # data de referência (30/09/2026) entra nas pendências e é classificada como vencida
    # ou a vencer conforme a data de vencimento
    records = [
        *_sample_rag_financial_sources(),
        _make_financial_chunk_source(
            "chunk-fin-aug-overdue",
            {
                "id_transacao": "FIN-2026-000A",
                "data": "2026-08-10",
                "produtor_id": "P004",
                "produtor_nome": "Ana Lúcia Bezerra da Costa",
                "tipo": "venda",
                "produto": "alface",
                "valor_total": "300.00",
                "status_pagamento": "pendente",
                "data_vencimento": "2026-09-15",
                "data_pagamento": "",
            },
        ),
        _make_financial_chunk_source(
            "chunk-fin-aug-upcoming",
            {
                "id_transacao": "FIN-2026-000B",
                "data": "2026-08-25",
                "produtor_id": "P004",
                "produtor_nome": "Ana Lúcia Bezerra da Costa",
                "tipo": "venda",
                "produto": "coentro",
                "valor_total": "200.00",
                "status_pagamento": "pendente",
                "data_vencimento": "2026-10-05",
                "data_pagamento": "",
            },
        ),
    ]

    calc = calculate_producer_financial_summary(
        "P004",
        period_start="2026-09-01",
        period_end="2026-09-30",
        reference_date="2026-09-30",
        financial_records=records,
    )

    assert calc.sales_in_period.formatted_total == "R$ 1.020,00"
    assert calc.sales_in_period.transaction_ids == ["FIN-2026-006", "FIN-2026-007"]
    assert calc.pending_overdue.formatted_total == "R$ 300,00"
    assert calc.pending_overdue.transaction_ids == ["FIN-2026-000A"]
    assert calc.pending_overdue.due_dates == ["2026-09-15"]
    assert calc.pending_upcoming.formatted_total == "R$ 1.220,00"
    assert calc.pending_upcoming.transaction_ids == [
        "FIN-2026-006",
        "FIN-2026-007",
        "FIN-2026-000B",
    ]
    assert calc.pending_total.formatted_total == "R$ 1.520,00"


@pytest.mark.asyncio
async def test_ambiguous_producer_name_requests_clarification_without_aggregating_multiple_producers() -> None:
    # Revisão PR #47 item 4 (ambiguidade de produtor): consultar apenas "Maria" quando há
    # múltiplos produtores com "Maria" no nome (P001 e P006) não pode agregar transações nem
    # atribuir o total ao primeiro produtor; deve pedir esclarecimento.
    records = [
        *_sample_rag_financial_sources(),
        _make_financial_chunk_source(
            "chunk-fin-008",
            {
                "id_transacao": "FIN-2026-008",
                "data": "2026-09-12",
                "produtor_id": "P006",
                "produtor_nome": "Severina Maria do Nascimento",
                "tipo": "venda",
                "produto": "banana prata",
                "valor_total": "600.00",
                "status_pagamento": "pendente",
                "data_vencimento": "2026-10-12",
                "data_pagamento": "",
            },
        ),
        _make_financial_chunk_source(
            "chunk-fin-014",
            {
                "id_transacao": "FIN-2026-014",
                "data": "2026-09-14",
                "produtor_id": "P014",
                "produtor_nome": "Mariana de Fátima Cordeiro",
                "tipo": "venda",
                "produto": "morango",
                "valor_total": "500.00",
                "status_pagamento": "pago",
                "data_vencimento": "2026-09-20",
                "data_pagamento": "2026-09-20",
            },
        ),
    ]
    provider = InMemoryFinancialRecordsProvider(records)

    calc = calculate_producer_financial_summary(
        "Maria",
        period="2026-09",
        reference_date="2026-09-30",
        financial_records_provider=provider,
    )
    assert calc.is_ambiguous_producer is True
    assert calc.has_any_records is False
    assert calc.sales_in_period.total_amount == Decimal("0.00")
    assert calc.all_transaction_ids == []
    assert [m.producer_id for m in calc.matching_producers] == ["P001", "P006"]
    assert calc.clarification_message is not None
    assert "P001" in calc.clarification_message
    assert "P006" in calc.clarification_message

    # Via orchestrate_request(), retorna pedido de esclarecimento sem inventar nem somar valores
    orch_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-ambiguous-maria",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-09-30",
            message_text="Gere o resumo financeiro da Maria em setembro de 2026.",
        ),
        financial_records_provider=provider,
    )
    assert isinstance(orch_resp.result, ConsultationResponse)
    assert orch_resp.result.has_sufficient_data is False
    assert orch_resp.result.source_ids == []
    assert "P001" in orch_resp.result.answer
    assert "P006" in orch_resp.result.answer
    assert "R$ 1.690,00" not in orch_resp.result.answer
    assert any(g.kind == "lacuna" for g in orch_resp.result.gaps_and_divergences)

    # Já uma consulta inequívoca ("Ana") não deve colidir por substring com "Mariana"
    ana_calc = calculate_producer_financial_summary(
        "Ana",
        period="2026-09",
        reference_date="2026-09-30",
        financial_records_provider=provider,
    )
    assert ana_calc.is_ambiguous_producer is False
    assert ana_calc.producer_id == "P004"
    assert ana_calc.sales_in_period.formatted_total == "R$ 1.020,00"


@pytest.mark.asyncio
async def test_financial_summary_informs_when_no_records_are_found_for_producer() -> None:
    # Critério 5 da #40: quando a ferramenta não encontra registros para o cálculo,
    # o assistente informa que a informação não foi encontrada na base
    records = _sample_rag_financial_sources()

    runner = FakeFinancialConsultationRunner(
        {
            "answer": "Não foram encontrados registros para P999.",
            "reference_date_used": "2026-09-30",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": False,
        }
    )

    payload = ConsultationInput(
        question="Qual o resumo financeiro do produtor P999 em setembro de 2026?",
        reference_date="2026-09-30",
        producer_id="P999",
        period_start="2026-09-01",
        period_end="2026-09-30",
        sources=records,
        financial_records=records,
    )
    response = await answer_document_consultation(payload, runner=runner)

    assert response.has_sufficient_data is False
    assert response.source_ids == []
    assert response.cited_sources == []
    assert "não foram encontrados registros" in response.answer.lower()
    assert any(g.kind == "lacuna" for g in response.gaps_and_divergences)


def test_financial_tool_restricts_records_strictly_to_financeiro_csv_origin() -> None:
    # Revisão PR #47 item 4 (origem dos registros): registros com campos compatíveis
    # vindos de outros arquivos (ex.: relatorio_paralelo.csv, lotes.csv ou sem nome de arquivo)
    # devem ser ignorados; apenas registros efetivamente de financeiro.csv entram no cálculo.
    valid_chunk_p004 = SimpleNamespace(
        id="uuid-chunk-fin-006",
        document_id="uuid-doc-fin",
        record_id="FIN-2026-006",
        record_fields={
            "id_transacao": "FIN-2026-006",
            "data": "2026-09-08",
            "produtor_id": "P004",
            "produtor_nome": "Ana Lúcia Bezerra da Costa",
            "tipo": "venda",
            "valor_total": "750.00",
            "data_vencimento": "2026-10-23",
            "data_pagamento": "",
        },
        content="id_transacao=FIN-2026-006; produtor_id=P004; valor_total=750.00",
        document=SimpleNamespace(original_filename="financeiro.csv"),
    )
    foreign_csv_same_fields = _make_financial_chunk_source(
        "chunk-foreign-001",
        {
            "id_transacao": "EXT-2026-999",
            "data": "2026-09-08",
            "produtor_id": "P004",
            "produtor_nome": "Ana Lúcia Bezerra da Costa",
            "tipo": "venda",
            "valor_total": "9999.00",
            "data_vencimento": "2026-10-23",
            "data_pagamento": "",
        },
        document_id="doc-outro-csv",
        document_name="relatorio_paralelo.csv",
    )
    foreign_orm_chunk = SimpleNamespace(
        id="uuid-foreign-orm",
        document_id="uuid-doc-other",
        record_id="EXT-2026-888",
        record_fields={
            "id_transacao": "EXT-2026-888",
            "data": "2026-09-08",
            "produtor_id": "P004",
            "produtor_nome": "Ana Lúcia Bezerra da Costa",
            "tipo": "venda",
            "valor_total": "5000.00",
            "data_vencimento": "2026-10-23",
            "data_pagamento": "",
        },
        content="id_transacao=EXT-2026-888; produtor_id=P004; valor_total=5000.00",
        document=SimpleNamespace(original_filename="extrato_externo.csv"),
    )
    dict_without_document_name = {
        "source_id": "dict-no-doc",
        "record_fields": {
            "id_transacao": "EXT-2026-777",
            "data": "2026-09-08",
            "produtor_id": "P004",
            "produtor_nome": "Ana Lúcia Bezerra da Costa",
            "tipo": "venda",
            "valor_total": "3000.00",
            "data_vencimento": "2026-10-23",
            "data_pagamento": "",
        },
    }
    non_financial_lot = ConsultationSourceItem(
        source_id="chunk-lot-0094",
        source_kind=SourceKind.LOT_RECORD,
        document_name="lotes.csv",
        reference_label="LOT-2026-0094",
        record_fields={"lote_id": "LOT-2026-0094", "produtor_id": "P004", "produto": "alface"},
        content="lote_id=LOT-2026-0094; produtor_id=P004; produto=alface",
    )
    non_financial_cert = ConsultationSourceItem(
        source_id="chunk-cert-p004",
        source_kind=SourceKind.DOCUMENT_CHUNK,
        document_name="cert_p004.txt",
        content="Certificação orgânica vigente para hortaliças.",
    )

    calc = calculate_producer_financial_summary(
        "P004",
        period="2026-09",
        reference_date="2026-09-30",
        financial_records=[
            valid_chunk_p004,
            foreign_csv_same_fields,
            foreign_orm_chunk,
            dict_without_document_name,
            non_financial_lot,
            non_financial_cert,
        ],
    )
    assert calc.sales_in_period.formatted_total == "R$ 750,00"
    assert calc.sales_in_period.transaction_ids == ["FIN-2026-006"]
    assert calc.sales_in_period.source_ids == ["uuid-chunk-fin-006"]
    assert calc.source_document == "financeiro.csv"


@pytest.mark.asyncio
async def test_document_queries_about_contract_payment_terms_or_sale_prices_are_not_blocked_as_financial_summaries() -> None:
    # Garante que consultas documentais sobre condição de pagamento de contrato,
    # preço de venda ou pendência de certificação não sejam confundidas com resumo financeiro
    from datetime import date

    from api.agents.consultation import (
        extract_financial_query_params,
        is_financial_consultation_query,
    )

    assert (
        is_financial_consultation_query(
            "Qual a condição de pagamento do Contrato nº 045/2026-PNAE?"
        )
        is False
    )
    assert (
        is_financial_consultation_query(
            "Qual o preço de venda da goiaba na tabela de preços de outubro?"
        )
        is False
    )
    assert (
        is_financial_consultation_query(
            "Quais as pendências da certificação orgânica da produtora P004?"
        )
        is False
    )

    # Data completa de referência (ISO ou BR) é extraída como reference_date sem virar período explícito
    params = extract_financial_query_params(
        "Gere o resumo financeiro de P001 com data de referência em 2026-10-15.",
        reference_date=date(2026, 11, 19),
    )
    assert params.producer == "P001"
    assert params.period_start is None
    assert params.period_end is None
    assert params.reference_date == date(2026, 10, 15)
    assert params.has_invalid_date is False

    contract_source = ConsultationSourceItem(
        source_id="chunk-contrato-pnae",
        document_id="doc-contrato-pnae",
        document_name="contrato_pnae_garanhuns.txt",
        reference_label="Contrato nº 045/2026-PNAE",
        content="PAGAMENTO: Empenho com prazo de até 45 dias após atesto do recebimento.",
    )
    runner = FakeFinancialConsultationRunner(
        {
            "answer": (
                "Considerando 30/10/2026, o Contrato nº 045/2026-PNAE prevê pagamento "
                "por empenho em até 45 dias após atesto (contrato_pnae_garanhuns.txt)."
            ),
            "reference_date_used": "2026-10-30",
            "source_ids": ["chunk-contrato-pnae"],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        }
    )

    orch_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-contract-payment-terms",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-10-30",
            message_text="Qual a condição de pagamento do Contrato nº 045/2026-PNAE?",
            sources=[contract_source],
        ),
        consultation_runner=runner,
    )
    assert isinstance(orch_resp.result, ConsultationResponse)
    assert orch_resp.result.has_sufficient_data is True
    assert orch_resp.result.source_ids == ["chunk-contrato-pnae"]
    assert "45 dias" in orch_resp.result.answer


@pytest.mark.asyncio
async def test_orchestrate_request_respects_explicit_financial_reference_date_distinct_from_interaction_date() -> None:
    # 2ª revisão PR #47 item 1: interação em 19/11/2026 pedindo resumo de P004 para setembro/2026
    # com referência em 30/09/2026 deve classificar R$ 1.020,00 como A VENCER em 23/10/2026
    # (e não vencidos), usando 2026-09-30 no cálculo e em reference_date_used.
    all_records = _sample_rag_financial_sources()
    provider = InMemoryFinancialRecordsProvider(all_records)
    dummy_runner = FakeFinancialConsultationRunner(
        {
            "answer": "Resumo preliminar.",
            "reference_date_used": "2026-11-19",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        }
    )

    orch_resp = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-ref-diff-1",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Gere o resumo financeiro de P004 para setembro de 2026, "
                "com referência em 30/09/2026."
            ),
            sources=[],
        ),
        consultation_runner=dummy_runner,
        financial_records_provider=provider,
    )

    assert isinstance(orch_resp.result, ConsultationResponse)
    assert orch_resp.result.reference_date_used == "2026-09-30"
    assert "30/09/2026 (2026-09-30)" in orch_resp.result.answer
    assert "Pendências a vencer em 23/10/2026 (2026-10-23): R$ 1.020,00" in orch_resp.result.answer
    assert "Pendências vencidas" not in orch_resp.result.answer
    assert orch_resp.result.source_ids == ["chunk-fin-006", "chunk-fin-007"]
    # A data da interação (19/11/2026) continua preservada no histórico da sessão
    assert orch_resp.session_history[0].received_at == "2026-11-19"

    # Também funciona quando a referência vem por extenso ANTES do período
    orch_written_ref = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-ref-diff-written",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Com referência em 30 de setembro de 2026, gere o resumo financeiro "
                "de P004 para setembro de 2026."
            ),
            sources=[],
        ),
        consultation_runner=dummy_runner,
        financial_records_provider=provider,
    )
    assert isinstance(orch_written_ref.result, ConsultationResponse)
    assert orch_written_ref.result.reference_date_used == "2026-09-30"
    assert "Pendências a vencer em 23/10/2026" in orch_written_ref.result.answer

    # Sem referência explícita na pergunta, usa a data da interação (19/11/2026 -> vencido!)
    orch_interaction_ref = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-ref-interaction",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text="Gere o resumo financeiro de P004 para setembro de 2026.",
            sources=[],
        ),
        consultation_runner=dummy_runner,
        financial_records_provider=provider,
    )
    assert isinstance(orch_interaction_ref.result, ConsultationResponse)
    assert orch_interaction_ref.result.reference_date_used == "2026-11-19"
    assert "Pendências vencidas (vencimento em 23/10/2026 (2026-10-23)): R$ 1.020,00" in orch_interaction_ref.result.answer


@pytest.mark.asyncio
async def test_financial_query_without_tool_execution_or_with_divergent_tool_params_never_returns_unverified_values() -> None:
    # 2ª revisão PR #47 item 2:
    # (A) Quando produtor não é identificado e o modelo NÃO executa a ferramenta financeira,
    #     NÃO pode cair na reconciliação documental comum nem exibir valores sem cálculo determinístico.
    # (B) Quando os parâmetros já foram extraídos da pergunta, chamada posterior da ferramenta
    #     com produtor/período/referência divergentes NÃO pode substituir o cálculo solicitado.
    # (C) Quando produtor não foi extraído e a ferramenta é chamada com período ou referência
    #     divergentes do pedido, a chamada divergente é rejeitada e pede esclarecimento.
    # (D) Quando a ferramenta é chamada com parâmetros compatíveis mas valores adulterados no evento,
    #     o recálculo determinístico sobre os registros exaustivos prevalece.
    all_records = _sample_rag_financial_sources()
    provider = InMemoryFinancialRecordsProvider(all_records)
    tool_fn = build_financial_summary_tool(financial_records_provider=provider)

    # (A) Produtor não identificado + modelo NÃO executa a ferramenta + tenta inventar R$ 1.500,00
    no_tool_runner = FakeFinancialConsultationRunner(
        {
            "answer": "A produtora tem R$ 1.500,00 a receber (FIN-2026-006 em financeiro.csv).",
            "reference_date_used": "2026-09-30",
            "source_ids": ["chunk-fin-006"],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        }
    )
    resp_no_tool = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-no-tool",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Quanto essa produtora tem a receber em setembro de 2026 "
                "com referência em 30/09/2026?"
            ),
            sources=[all_records[3]],
        ),
        consultation_runner=no_tool_runner,
        financial_records_provider=provider,
    )
    assert isinstance(resp_no_tool.result, ConsultationResponse)
    assert resp_no_tool.result.has_sufficient_data is False
    assert resp_no_tool.result.source_ids == []
    assert resp_no_tool.result.cited_sources == []
    assert resp_no_tool.result.reference_date_used == "2026-09-30"
    assert "R$ 1.500,00" not in resp_no_tool.result.answer
    assert "produtor" in resp_no_tool.result.answer.lower()
    assert any(g.kind == "lacuna" for g in resp_no_tool.result.gaps_and_divergences)

    # (B) Parâmetros extraídos da pergunta (P004, set/2026, ref 30/09/2026), mas runner
    #     emite chamada de ferramenta divergente para P001 em out/2026 com ref 19/11/2026
    divergent_p001_payload = tool_fn("P001", "2026-10-01", "2026-10-31", "2026-11-19")
    divergent_runner_b = FakeFinancialConsultationRunner(
        {
            "answer": "Resumo de P001: R$ 940,00.",
            "reference_date_used": "2026-11-19",
            "source_ids": ["chunk-fin-001", "chunk-fin-002"],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
        tool_function_response=divergent_p001_payload,
    )
    resp_extracted_protected = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-divergent-extracted",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Gere o resumo financeiro de P004 para setembro de 2026, "
                "com referência em 30/09/2026."
            ),
            sources=[],
        ),
        consultation_runner=divergent_runner_b,
        financial_records_provider=provider,
    )
    assert isinstance(resp_extracted_protected.result, ConsultationResponse)
    assert resp_extracted_protected.result.reference_date_used == "2026-09-30"
    assert "P004" in resp_extracted_protected.result.answer
    assert "R$ 1.020,00" in resp_extracted_protected.result.answer
    assert "Pendências a vencer em 23/10/2026" in resp_extracted_protected.result.answer
    assert "R$ 940,00" not in resp_extracted_protected.result.answer
    assert resp_extracted_protected.result.source_ids == ["chunk-fin-006", "chunk-fin-007"]

    # (C) Produtor não extraído, mas período (set/2026) e referência (30/09/2026) foram solicitados;
    #     ferramenta chamada com referência divergente (2026-11-19) é rejeitada e pede esclarecimento
    divergent_ref_payload = tool_fn("P004", "2026-09-01", "2026-09-30", "2026-11-19")
    divergent_runner_c = FakeFinancialConsultationRunner(
        {
            "answer": "R$ 1.020,00 vencidos.",
            "reference_date_used": "2026-11-19",
            "source_ids": ["chunk-fin-006", "chunk-fin-007"],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
        tool_function_response=divergent_ref_payload,
    )
    resp_divergent_unextracted = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-divergent-unextracted",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Quanto essa produtora tem a receber em setembro de 2026 "
                "com referência em 30/09/2026?"
            ),
            sources=[],
        ),
        consultation_runner=divergent_runner_c,
        financial_records_provider=provider,
    )
    assert isinstance(resp_divergent_unextracted.result, ConsultationResponse)
    assert resp_divergent_unextracted.result.has_sufficient_data is False
    assert resp_divergent_unextracted.result.source_ids == []
    assert resp_divergent_unextracted.result.reference_date_used == "2026-09-30"
    assert "R$ 1.020,00" not in resp_divergent_unextracted.result.answer
    assert "divergem" in resp_divergent_unextracted.result.answer.lower()

    # (D) Produtor não extraído, chamada de ferramenta com parâmetros compatíveis mas valor adulterado
    #     no payload do evento -> recálculo determinístico sobre registros exaustivos restaura R$ 1.020,00
    tampered_matching_payload = tool_fn("P004", "2026-09-01", "2026-09-30", "2026-09-30")
    tampered_matching_payload["sales_in_period"]["formatted_total"] = "R$ 99.999,00"
    tampered_runner = FakeFinancialConsultationRunner(
        {
            "answer": "Vendas de R$ 99.999,00.",
            "reference_date_used": "2026-09-30",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        },
        tool_function_response=tampered_matching_payload,
    )
    resp_reverified = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-reverified",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Quanto essa produtora tem a receber em setembro de 2026 "
                "com referência em 30/09/2026?"
            ),
            sources=[],
        ),
        consultation_runner=tampered_runner,
        financial_records_provider=provider,
    )
    assert isinstance(resp_reverified.result, ConsultationResponse)
    assert resp_reverified.result.has_sufficient_data is True
    assert "R$ 1.020,00" in resp_reverified.result.answer
    assert "R$ 99.999,00" not in resp_reverified.result.answer
    assert resp_reverified.result.reference_date_used == "2026-09-30"

    # (E) Data inválida na pergunta (ex.: 31/02/2026) solicita esclarecimento sem falhar com exceção
    resp_invalid_date = await orchestrate_request(
        OrchestratorRequest(
            session_id="chat-fin-invalid-date",
            flow=OrchestratorFlow.CONSULTATION,
            received_at="2026-11-19",
            message_text=(
                "Gere o resumo financeiro de P004 para setembro de 2026 "
                "com referência em 31/02/2026."
            ),
            sources=[],
        ),
        financial_records_provider=provider,
    )
    assert isinstance(resp_invalid_date.result, ConsultationResponse)
    assert resp_invalid_date.result.has_sufficient_data is False
    assert resp_invalid_date.result.source_ids == []
    assert "inválida" in resp_invalid_date.result.answer.lower()
