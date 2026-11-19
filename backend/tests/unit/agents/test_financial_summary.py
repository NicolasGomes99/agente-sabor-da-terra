import json
from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types

from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    ConsultationInput,
    ConsultationResponse,
    ConsultationSourceItem,
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
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.app_name = "sabor_da_terra_consultation"
        self.session_service = FakeFinancialSessionService()
        self._response_payload = response_payload
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
        session.state[CONSULTATION_OUTPUT_KEY] = self._response_payload
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
    sources = _sample_rag_financial_sources()
    agent = create_consultation_agent(model="gemini-3.8-flash", sources=sources)
    assert len(agent.tools) == 1
    tool_fn = build_financial_summary_tool(sources)
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
    sources = _sample_rag_financial_sources()

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
        sources=sources,
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
    sources = _sample_rag_financial_sources()

    sept_calc = calculate_producer_financial_summary(
        "P001",
        period_start="2026-09-01",
        period_end="2026-09-30",
        reference_date="2026-09-30",
        sources=sources,
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

    # Simula o modelo omitindo parte dos números para verificar que a reconciliação
    # financeira preserva todos os valores da ferramenta (RNF04) e cita as fontes
    runner_sept = FakeFinancialConsultationRunner(
        {
            "answer": "Resumo parcial da produtora P001.",
            "reference_date_used": "2026-09-30",
            "source_ids": [],
            "cited_sources": [],
            "gaps_and_divergences": [],
            "has_sufficient_data": True,
        }
    )
    resp_sept, _ = await answer_producer_financial_summary(
        "P001",
        period_start="2026-09-01",
        period_end="2026-09-30",
        reference_date="2026-09-30",
        sources=sources,
        runner=runner_sept,
    )
    assert "R$ 1.090,00" in resp_sept.answer
    assert "R$ 150,00" in resp_sept.answer
    assert "R$ 940,00" in resp_sept.answer
    assert "02/10/2026" in resp_sept.answer
    assert "FIN-2026-001" in resp_sept.answer
    assert "FIN-2026-002" in resp_sept.answer
    assert "FIN-2026-015" in resp_sept.answer
    assert resp_sept.source_ids == ["chunk-fin-001", "chunk-fin-002", "chunk-fin-015"]

    # Em outubro/2026 (referência 31/10/2026), os R$ 940,00 de FIN-2026-001 e FIN-2026-002
    # (pagos em 01/10/2026) entram nos pagamentos registrados de outubro e saem das pendências
    oct_calc = calculate_producer_financial_summary(
        "P001",
        period_start="2026-10-01",
        period_end="2026-10-31",
        reference_date="2026-10-31",
        sources=sources,
    )
    assert oct_calc.sales_in_period.has_records is False
    assert oct_calc.registered_payments_in_period.formatted_total == "R$ 940,00"
    assert oct_calc.registered_payments_in_period.transaction_ids == [
        "FIN-2026-001",
        "FIN-2026-002",
    ]
    assert oct_calc.pending_total.has_records is False


def test_prior_period_unpaid_sales_are_included_in_pending_and_classified_as_overdue_or_upcoming() -> None:
    # Critério 3 da #40: venda de período anterior (agosto/2026) ainda sem pagamento na
    # data de referência (30/09/2026) entra nas pendências e é classificada como vencida
    # ou a vencer conforme a data de vencimento
    sources = [
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
        sources=sources,
    )

    # As vendas do período (setembro) continuam sendo apenas FIN-2026-006 e FIN-2026-007 (R$ 1.020,00)
    assert calc.sales_in_period.formatted_total == "R$ 1.020,00"
    assert calc.sales_in_period.transaction_ids == ["FIN-2026-006", "FIN-2026-007"]

    # A venda de agosto com vencimento em 15/09/2026 (< 30/09/2026) entra como vencida (R$ 300,00)
    assert calc.pending_overdue.formatted_total == "R$ 300,00"
    assert calc.pending_overdue.transaction_ids == ["FIN-2026-000A"]
    assert calc.pending_overdue.due_dates == ["2026-09-15"]

    # A venda de agosto com vencimento em 05/10/2026 (>= 30/09/2026) soma-se às de setembro a vencer (R$ 1.220,00)
    assert calc.pending_upcoming.formatted_total == "R$ 1.220,00"
    assert calc.pending_upcoming.transaction_ids == [
        "FIN-2026-006",
        "FIN-2026-007",
        "FIN-2026-000B",
    ]
    assert calc.pending_total.formatted_total == "R$ 1.520,00"


@pytest.mark.asyncio
async def test_financial_summary_informs_when_no_records_are_found_for_producer() -> None:
    # Critério 5 da #40: quando a ferramenta não encontra registros para o cálculo,
    # o assistente informa que a informação não foi encontrada na base
    sources = _sample_rag_financial_sources()

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
        sources=sources,
    )
    response = await answer_document_consultation(payload, runner=runner)

    assert response.has_sufficient_data is False
    assert response.source_ids == []
    assert response.cited_sources == []
    assert "não foram encontrados registros" in response.answer.lower()
    assert any(g.kind == "lacuna" for g in response.gaps_and_divergences)


def test_financial_tool_accepts_document_chunk_like_objects_and_ignores_non_financial_sources() -> None:
    chunk_like_p004 = SimpleNamespace(
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
        sources=[chunk_like_p004, non_financial_lot, non_financial_cert],
    )
    assert calc.sales_in_period.formatted_total == "R$ 750,00"
    assert calc.sales_in_period.transaction_ids == ["FIN-2026-006"]
    assert calc.sales_in_period.source_ids == ["uuid-chunk-fin-006"]
    assert calc.source_document == "financeiro.csv"
