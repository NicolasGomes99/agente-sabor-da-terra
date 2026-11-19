import json
from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from google.genai import types

from api.agents.consultation.schemas import ConsultationSourceItem, SourceKind
from api.agents.producer_suggestion import (
    PRODUCER_SUGGESTION_OUTPUT_KEY,
    BalanceStatus,
    CandidateProofStatus,
    CapacityComparisonStatus,
    CertificationCoverageStatus,
    InMemoryProducerSuggestionToolProvider,
    OrderItemBalanceContract,
    OrderToolContract,
    ProducerCatalogItemContract,
    ProducerSuggestionInput,
    ProducerSuggestionResponse,
    ProductCatalogRef,
    UnitEquivalence,
    build_producer_suggestion_instruction,
    convert_quantity_with_known_equivalence,
    create_producer_suggestion_agent,
    producer_suggestion_agent,
    root_agent,
    suggest_producers_for_order,
)
from api.schemas.producer import ProducerResponse
from api.schemas.product import ProductResponse


class FakeSuggestionSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id=f"session-sug-{len(self.sessions) + 1}",
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


class FakeSuggestionRunner:
    def __init__(
        self,
        response_payload: dict[str, Any] | ProducerSuggestionResponse | None = None,
    ) -> None:
        self.app_name = "sabor_da_terra_producer_suggestion"
        self.session_service = FakeSuggestionSessionService()
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

        if self._response_payload is None:
            # Extrai o JSON da avaliação determinística do prompt como saída padrão simulada
            start_tag = "<avaliacao_ferramentas_aplicacao>\n"
            end_tag = "\n</avaliacao_ferramentas_aplicacao>"
            raw_json = self.last_prompt_text.split(start_tag, maxsplit=1)[1].split(
                end_tag, maxsplit=1
            )[0]
            payload_dict: Any = json.loads(raw_json)
        elif isinstance(self._response_payload, ProducerSuggestionResponse):
            payload_dict = self._response_payload.model_dump()
        else:
            payload_dict = self._response_payload

        session.state[PRODUCER_SUGGESTION_OUTPUT_KEY] = payload_dict
        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(payload_dict, ensure_ascii=False))],
            ),
            is_final_response=lambda: True,
        )


def test_create_producer_suggestion_agent_and_google_genai_t_schema_compatibility() -> None:
    from google.genai._transformers import t_schema

    agent = create_producer_suggestion_agent(model="gemini-3.8-flash")
    assert agent.name == "producer_suggestion_agent"
    assert agent.output_schema is ProducerSuggestionResponse
    assert agent.output_key == PRODUCER_SUGGESTION_OUTPUT_KEY
    assert len(agent.tools) == 3
    assert producer_suggestion_agent.name == "producer_suggestion_agent"
    assert root_agent is producer_suggestion_agent

    instruction = build_producer_suggestion_instruction(SimpleNamespace())
    assert "RF14" in instruction
    assert "RF26" in instruction
    assert "RF27" in instruction

    # Garante compatibilidade estrita do output_schema com o SDK google-genai
    schema = t_schema(None, ProducerSuggestionResponse)
    assert schema is not None


@pytest.mark.asyncio
async def test_item_balance_uses_remaining_50kg_of_100kg_and_handles_zero_and_indetermined_balances() -> None:
    # Critérios 1, 2, 3 e 4 da #25:
    # - 100 kg solicitados com 50 kg em alocações vigentes -> usa saldo de 50 kg
    # - saldo zero -> informa que já está integralmente alocado
    # - saldo indeterminado -> explica a pendência e deixa a quantidade em aberto
    order = OrderToolContract(
        order_id="PED-2026-100",
        buyer="Mercado Bom Preço",
        delivery_start_date="2026-11-05",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-goiaba",
                product_id="prod-goiaba",
                product_name="Goiaba paluma",
                requested_quantity=Decimal(100),
                allocated_quantity=Decimal(50),
                remaining_balance=Decimal(50),
                unit="kg",
            ),
            OrderItemBalanceContract(
                order_item_id="item-banana",
                product_id="prod-banana",
                product_name="Banana prata",
                requested_quantity=Decimal(80),
                allocated_quantity=Decimal(80),
                remaining_balance=Decimal(0),
                unit="kg",
            ),
            OrderItemBalanceContract(
                order_item_id="item-couve",
                product_id="prod-couve",
                product_name="Couve",
                requested_quantity=Decimal(40),
                allocated_quantity=None,
                remaining_balance=None,
                unit="maço",
                balance_status=BalanceStatus.INDETERMINED,
                balance_pending_reason=(
                    "Alocação existente com unidade ambígua ('40 maços (kg)')."
                ),
            ),
        ],
    )

    producers = [
        ProducerCatalogItemContract(
            producer_id="uuid-p001",
            code="P001",
            name="Maria das Graças Silva Ferreira",
            active=True,
            products=[
                ProductCatalogRef(product_id="prod-goiaba", product_name="Goiaba paluma"),
            ],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p006",
            code="P006",
            name="Severina Maria do Nascimento",
            active=True,
            products=[
                ProductCatalogRef(product_id="prod-banana", product_name="Banana prata"),
            ],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p009",
            code="P009",
            name="Marcos Vinícius da Rocha",
            active=True,
            products=[
                ProductCatalogRef(product_id="prod-couve", product_name="Couve"),
            ],
        ),
    ]

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=producers,
    )
    response = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-100", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )

    assert response.order_id == "PED-2026-100"
    assert response.buyer == "Mercado Bom Preço"
    by_item = {item.order_item_id: item for item in response.item_suggestions}

    # Item 1: usa saldo de 50 kg (não 100 kg)
    goiaba = by_item["item-goiaba"]
    assert goiaba.requested_quantity == 100.0
    assert goiaba.allocated_quantity == 50.0
    assert goiaba.remaining_balance == 50.0
    assert goiaba.balance_status == BalanceStatus.AVAILABLE
    assert "50 kg" in goiaba.allocation_message
    assert len(goiaba.candidates) == 1
    assert any("50 kg" in p for p in goiaba.candidates[0].pending_confirmations)

    # Item 2: saldo zero -> integralmente alocado, sem novas sugestões
    banana = by_item["item-banana"]
    assert banana.remaining_balance == 0.0
    assert banana.balance_status == BalanceStatus.FULLY_ALLOCATED
    assert "integralmente alocada" in banana.allocation_message.lower()
    assert banana.candidates == []

    # Item 3: saldo indeterminado -> explica pendência e mantém quantidade em aberto (None)
    couve = by_item["item-couve"]
    assert couve.remaining_balance is None
    assert couve.balance_status == BalanceStatus.INDETERMINED
    assert "indeterminado" in couve.allocation_message.lower()
    assert "em aberto" in couve.allocation_message.lower()
    assert "40 maços (kg)" in couve.allocation_message


@pytest.mark.asyncio
async def test_excludes_inactive_non_supplying_and_expired_or_uncovered_cert_producers_and_separates_proof_status() -> None:
    # Critérios 5, 6, 7 e 11 da #25 + US04 (contrato PNAE e DAP/CAF):
    # - exclui produtor inativo (P015), não fornecedor, certificado vencido (P008, mesmo com lote
    #   dizendo 'Certificação orgânica anexa') e certificado que não cobre o produto
    # - separa candidatos com comprovação suficiente dos que dependem de confirmação
    order = OrderToolContract(
        order_id="PED-2026-004",
        buyer="Prefeitura de Garanhuns - PNAE",
        conditions="Conforme Contrato nº 045/2026-PNAE; mel silvestre com certificação orgânica.",
        contract_reference="Contrato nº 045/2026-PNAE",
        delivery_start_date="2026-11-04",
        delivery_end_date="2026-11-08",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-mel",
                product_id="prod-mel",
                product_name="Mel silvestre",
                requested_quantity=Decimal(20),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(20),
                unit="kg",
                requires_organic_certification=True,
            ),
        ],
    )

    producers = [
        ProducerCatalogItemContract(
            producer_id="uuid-p002",
            code="P002",
            name="José Antônio dos Santos",
            active=True,
            products=[ProductCatalogRef(product_id="prod-mel", product_name="Mel silvestre")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p018",
            code="P018",
            name="Débora Cristina de Melo",
            active=True,
            products=[ProductCatalogRef(product_id="prod-mel", product_name="Mel silvestre")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p008",
            code="P008",
            name="Josefa Alves de Souza",
            active=True,
            products=[ProductCatalogRef(product_id="prod-mel", product_name="Mel silvestre")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p015",
            code="P015",
            name="Geraldo Manoel Barbosa",
            active=False,
            products=[ProductCatalogRef(product_id="prod-mel", product_name="Mel silvestre")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p019",
            code="P019",
            name="Produtor Certificado Outro Produto",
            active=True,
            products=[ProductCatalogRef(product_id="prod-mel", product_name="Mel silvestre")],
        ),
    ]

    sources = [
        ConsultationSourceItem(
            source_id="src-contrato-pnae",
            document_id="doc-pnae",
            document_name="contrato_pnae_garanhuns.txt",
            reference_label="Contrato nº 045/2026-PNAE",
            content=(
                "CONTRATO Nº 045/2026-PNAE\n"
                "CONDIÇÕES OBRIGATÓRIAS:\n"
                "1. Todos os produtores devem possuir DAP ou CAF vigente\n"
                "2. Produtos orgânicos devem apresentar certificação válida\n"
                "3. Produtos de origem animal exigem registro SIE, SIM ou SISBI"
            ),
        ),
        ConsultationSourceItem(
            source_id="src-cert-p002",
            document_id="doc-cert-p002",
            document_name="cert_organica_jose_santos_P002.txt",
            reference_label="ORG-PE-2025-003198",
            content=(
                "Produtor: José Antônio dos Santos (P002)\n"
                "Data de Validade: 20/03/2027\n"
                "DAP/CAF: SDR/PE-2018-0031204 (validade: 31/12/2027)\n"
                "Registro SIE: PE-SIE-0842\n"
                "PRODUTOS CERTIFICADOS:\n"
                "1. Mel silvestre"
            ),
        ),
        ConsultationSourceItem(
            source_id="src-cert-p018",
            document_id="doc-cert-p018",
            document_name="cert_organica_debora_melo_P018.txt",
            reference_label="ORG-PE-2025-009876",
            content=(
                "Produtora: Débora Cristina de Melo (P018)\n"
                "Data de Validade: 28/02/2027\n"
                "DAP/CAF: SDR/PE-2021-0099112\n"
                "Registro SIE: PE-SIE-1500\n"
                "PRODUTOS CERTIFICADOS:\n"
                "1. Mel silvestre"
            ),
        ),
        ConsultationSourceItem(
            source_id="src-cert-p008",
            document_id="doc-cert-p008",
            document_name="cert_organica_josefa_souza_P008.txt",
            reference_label="ORG-PE-2024-003876",
            content=(
                "Produtora: Josefa Alves de Souza (P008)\n"
                "Data de Validade: 30/09/2026\n"
                "PRODUTOS CERTIFICADOS:\n"
                "1. Mel silvestre"
            ),
        ),
        ConsultationSourceItem(
            source_id="src-lot-p008",
            source_kind=SourceKind.LOT_RECORD,
            document_id="doc-lotes",
            document_name="lotes.csv",
            reference_label="LOT-2026-0104",
            content=(
                "lote_id=LOT-2026-0104; data_entrega=2026-10-01; produtor_id=P008; "
                "produtor_nome=Josefa Alves de Souza; produto=mel silvestre; "
                "quantidade_kg=10; observacao=Certificação orgânica anexa"
            ),
        ),
        ConsultationSourceItem(
            source_id="src-cert-p019",
            document_id="doc-cert-p019",
            document_name="cert_organica_p019.txt",
            reference_label="ORG-PE-2025-001111",
            content=(
                "Produtor: Produtor Certificado Outro Produto (P019)\n"
                "Data de Validade: 30/12/2027\n"
                "PRODUTOS CERTIFICADOS:\n"
                "1. Banana prata"
            ),
        ),
    ]

    # Simula modelo tentando indevidamente incluir o produtor inativo P015 e inventar source_id
    malicious_model_payload = {
        "order_id": "PED-2026-004",
        "buyer": "Prefeitura de Garanhuns - PNAE",
        "reference_date_used": "2026-10-30",
        "evaluated_delivery_start": "2026-11-04",
        "evaluated_delivery_end": "2026-11-08",
        "exact_delivery_date_used": False,
        "summary": "Sugiro P015 (inativo) e P008 com disponibilidade confirmada.",
        "item_suggestions": [
            {
                "order_item_id": "item-mel",
                "product_id": "prod-mel",
                "product_name": "Mel silvestre",
                "remaining_balance": 20.0,
                "unit": "kg",
                "balance_status": "disponivel",
                "allocation_message": "Saldo 20 kg.",
                "candidates": [
                    {
                        "producer_id": "uuid-p015",
                        "producer_code": "P015",
                        "producer_name": "Geraldo Manoel Barbosa",
                        "proof_status": "comprovacao_suficiente",
                        "availability_confirmed": True,
                        "source_ids": ["fonte-inventada-999"],
                    },
                    {
                        "producer_id": "uuid-p002",
                        "producer_code": "P002",
                        "producer_name": "José Antônio dos Santos",
                        "proof_status": "comprovacao_suficiente",
                        "availability_confirmed": True,
                        "source_ids": ["fonte-inventada-999"],
                    },
                ],
            }
        ],
        "source_ids": ["fonte-inventada-999"],
    }

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=producers,
        sources=sources,
    )
    response = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-004", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(malicious_model_payload),
    )

    mel_item = response.item_suggestions[0]
    cand_by_code = {c.producer_code: c for c in mel_item.candidates}
    excl_by_code = {e.producer_code: e for e in mel_item.excluded_producers}

    # P015 (inativo), P008 (certificado vencido) e P019 (não cobre mel) foram excluídos
    assert set(excl_by_code.keys()) == {"P015", "P008", "P019"}
    assert "inativo" in " ".join(excl_by_code["P015"].reasons).lower()
    assert "vencida" in " ".join(excl_by_code["P008"].reasons).lower()
    assert "não cobre" in " ".join(excl_by_code["P019"].reasons).lower()
    assert "P015" not in cand_by_code
    assert "P008" not in cand_by_code
    assert "P019" not in cand_by_code

    # P002 tem comprovação suficiente; P018 depende de confirmação da vigência do DAP/CAF (US04)
    assert set(cand_by_code.keys()) == {"P002", "P018"}
    assert cand_by_code["P002"].proof_status == CandidateProofStatus.SUFFICIENT_PROOF
    assert cand_by_code["P002"].certification_status == CertificationCoverageStatus.VALID_FULL
    assert cand_by_code["P002"].availability_confirmed is False

    assert cand_by_code["P018"].proof_status == CandidateProofStatus.NEEDS_CONFIRMATION
    assert any("dap/caf" in p.lower() and "vigência" in p.lower() for p in cand_by_code["P018"].pending_confirmations)
    assert "src-contrato-pnae" in cand_by_code["P018"].source_ids
    assert "src-cert-p018" in cand_by_code["P018"].source_ids

    # Fonte inventada foi descartada e resumo separa os dois grupos
    assert "fonte-inventada-999" not in response.source_ids
    assert "Candidatos com comprovação suficiente:" in response.summary
    assert "Candidatos que ainda dependem de confirmação:" in response.summary


@pytest.mark.asyncio
async def test_organic_certification_exact_delivery_date_vs_full_interval_vs_partial_interval() -> None:
    # Critérios 7 e 8 da #25:
    # P004 possui certificado orgânico válido até 01/12/2026 para alface.
    # Pedido com intervalo de 28/11/2026 a 03/12/2026:
    # 1) Sem data exata -> cobertura parcial (28/11/2026 a 01/12/2026), pede confirmação da data
    # 2) Com data exata 30/11/2026 -> vigente integralmente na data exata
    # 3) Com data exata 02/12/2026 -> vencida na data exata (excluída)
    order = OrderToolContract(
        order_id="PED-2026-DEC",
        buyer="Hospital São Francisco",
        conditions="Hortaliças com certificação orgânica obrigatória.",
        delivery_start_date="2026-11-28",
        delivery_end_date="2026-12-03",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-alface",
                product_id="prod-alface",
                product_name="Alface",
                requested_quantity=Decimal(100),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(100),
                unit="unidade",
                requires_organic_certification=True,
            ),
        ],
    )
    p004 = ProducerCatalogItemContract(
        producer_id="uuid-p004",
        code="P004",
        name="Ana Lúcia Bezerra da Costa",
        active=True,
        products=[ProductCatalogRef(product_id="prod-alface", product_name="Alface")],
    )
    cert_p004 = ConsultationSourceItem(
        source_id="src-cert-p004",
        document_id="doc-cert-p004",
        document_name="cert_organica_ana_bezerra_P004.txt",
        reference_label="ECO-BR-2024-PE-0891",
        content=(
            "Produtora: Ana Lúcia Bezerra da Costa (P004)\n"
            "Data de Validade: 01/12/2026\n"
            "PRODUTOS CERTIFICADOS:\n"
            "1. Alface (Lactuca sativa)\n"
            "2. Coentro"
        ),
    )
    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=[p004],
        sources=[cert_p004],
    )

    # Caso 1: apenas o intervalo -> cobertura parcial 28/11/2026 a 01/12/2026
    partial_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-DEC", reference_date="2026-11-20"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert partial_resp.exact_delivery_date_used is False
    partial_cand = partial_resp.item_suggestions[0].candidates[0]
    assert partial_cand.certification_status == CertificationCoverageStatus.VALID_PARTIAL
    assert partial_cand.certification_covered_start == "2026-11-28"
    assert partial_cand.certification_covered_end == "2026-12-01"
    assert partial_cand.proof_status == CandidateProofStatus.NEEDS_CONFIRMATION
    assert any(
        "28/11/2026" in p and "01/12/2026" in p and "confirmar a data" in p.lower()
        for p in partial_cand.pending_confirmations
    )

    # Caso 2: data exata 30/11/2026 -> vigente integralmente na data exata
    exact_ok_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(
            order_id="PED-2026-DEC",
            reference_date="2026-11-20",
            exact_delivery_date="2026-11-30",
        ),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert exact_ok_resp.exact_delivery_date_used is True
    assert exact_ok_resp.evaluated_delivery_start == "2026-11-30"
    assert exact_ok_resp.evaluated_delivery_end == "2026-11-30"
    exact_cand = exact_ok_resp.item_suggestions[0].candidates[0]
    assert exact_cand.certification_status == CertificationCoverageStatus.VALID_FULL
    assert exact_cand.proof_status == CandidateProofStatus.SUFFICIENT_PROOF

    # Caso 3: data exata 02/12/2026 -> vencida em 01/12/2026 -> excluída
    exact_expired_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(
            order_id="PED-2026-DEC",
            reference_date="2026-11-20",
            exact_delivery_date="2026-12-02",
        ),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    expired_item = exact_expired_resp.item_suggestions[0]
    assert expired_item.candidates == []
    assert len(expired_item.excluded_producers) == 1
    assert expired_item.excluded_producers[0].producer_code == "P004"
    assert "01/12/2026" in " ".join(expired_item.excluded_producers[0].reasons)
    assert expired_item.insufficient_data is True


@pytest.mark.asyncio
async def test_capacity_comparison_respects_compatible_units_periods_and_known_equivalences() -> None:
    # Critério 9 da #25: compara demanda e capacidade em unidades e períodos compatíveis,
    # convertendo apenas quando houver equivalência conhecida
    converted_dz, desc_dz = convert_quantity_with_known_equivalence(
        Decimal(24), "unidades", "dúzias"
    )
    assert converted_dz == Decimal(2)
    assert desc_dz is not None

    # Sem equivalência conhecida entre maço e kg -> não converte
    converted_unknown, _ = convert_quantity_with_known_equivalence(
        Decimal(150), "maços", "kg"
    )
    assert converted_unknown is None

    # Com equivalência explícita conhecida -> converte
    converted_custom, _ = convert_quantity_with_known_equivalence(
        Decimal(5),
        "caixas",
        "kg",
        product_name="Queijo coalho",
        unit_equivalences=[
            UnitEquivalence(
                from_unit="caixa",
                to_unit="kg",
                factor=Decimal(10),
                product_name="Queijo coalho",
            )
        ],
    )
    assert converted_custom == Decimal(50)

    order = OrderToolContract(
        order_id="PED-2026-CAP",
        buyer="Restaurante Raízes",
        delivery_start_date="2026-11-05",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-queijo",
                product_id="prod-queijo",
                product_name="Queijo coalho",
                requested_quantity=Decimal(5),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(5),
                unit="caixa",
            ),
            OrderItemBalanceContract(
                order_item_id="item-alface",
                product_id="prod-alface",
                product_name="Alface",
                requested_quantity=Decimal(300),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(300),
                unit="unidade",
            ),
            OrderItemBalanceContract(
                order_item_id="item-frango",
                product_id="prod-frango",
                product_name="Frango caipira",
                requested_quantity=Decimal(120),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(120),
                unit="kg",
            ),
            OrderItemBalanceContract(
                order_item_id="item-goiaba",
                product_id="prod-goiaba",
                product_name="Goiaba paluma",
                requested_quantity=Decimal(200),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(200),
                unit="kg",
            ),
        ],
    )

    producers = [
        ProducerCatalogItemContract(
            producer_id="uuid-p007",
            code="P007",
            name="Antônio Carlos Pereira Lima",
            active=True,
            products=[ProductCatalogRef(product_id="prod-queijo", product_name="Queijo coalho")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p004",
            code="P004",
            name="Ana Lúcia Bezerra da Costa",
            active=True,
            products=[ProductCatalogRef(product_id="prod-alface", product_name="Alface")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p017",
            code="P017",
            name="Wellington da Silva Monteiro",
            active=True,
            products=[ProductCatalogRef(product_id="prod-frango", product_name="Frango caipira")],
        ),
        ProducerCatalogItemContract(
            producer_id="uuid-p001",
            code="P001",
            name="Maria das Graças Silva Ferreira",
            active=True,
            products=[ProductCatalogRef(product_id="prod-goiaba", product_name="Goiaba paluma")],
        ),
    ]

    sources = [
        ConsultationSourceItem(
            source_id="src-cap-p007",
            document_name="cert_organica_antonio_lima_P007.txt",
            content="Produtor: Antônio Carlos Pereira Lima (P007)\nQueijo coalho: Produção: até 200 kg/semana",
        ),
        ConsultationSourceItem(
            source_id="src-cap-p004",
            document_name="hortalicas.txt",
            content="P004 - Ana Lúcia Bezerra\nProdutos: alface\nCapacidade: ~300 kg/semana",
        ),
        ConsultationSourceItem(
            source_id="src-cap-p017",
            document_name="sazonalidade.csv",
            content="Produtor P017 Wellington da Silva Monteiro; produto=frango caipira; escala limitada a ~80kg/semana",
        ),
        ConsultationSourceItem(
            source_id="src-cap-p001",
            document_name="cert_organica_maria_silva_P001.txt",
            content="Produtora: Maria das Graças Silva Ferreira (P001)\nGoiaba paluma: Produção estimada: 25 toneladas/ano",
        ),
    ]

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=producers,
        sources=sources,
    )
    resp = await suggest_producers_for_order(
        ProducerSuggestionInput(
            order_id="PED-2026-CAP",
            reference_date="2026-10-30",
            unit_equivalences=[
                UnitEquivalence(
                    from_unit="caixa",
                    to_unit="kg",
                    factor=Decimal(10),
                    product_name="Queijo coalho",
                )
            ],
        ),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )

    by_item = {i.order_item_id: i for i in resp.item_suggestions}

    # Queijo: 5 caixas = 50 kg <= 200 kg/semana (equivalência conhecida)
    assert (
        by_item["item-queijo"].candidates[0].capacity_comparison_status
        == CapacityComparisonStatus.COMPATIBLE
    )
    # Alface: 300 unidades vs 300 kg/semana -> unidade incompatível sem equivalência
    assert (
        by_item["item-alface"].candidates[0].capacity_comparison_status
        == CapacityComparisonStatus.INCOMPATIBLE_UNIT_OR_PERIOD
    )
    # Frango: 120 kg > 80 kg/semana -> acima da capacidade estimada
    assert (
        by_item["item-frango"].candidates[0].capacity_comparison_status
        == CapacityComparisonStatus.ABOVE_ESTIMATED_CAPACITY
    )
    # Goiaba: 200 kg entrega pontual vs 25 toneladas/ano -> período incompatível
    assert (
        by_item["item-goiaba"].candidates[0].capacity_comparison_status
        == CapacityComparisonStatus.INCOMPATIBLE_UNIT_OR_PERIOD
    )


@pytest.mark.asyncio
async def test_distinguishes_seasonality_capacity_historical_supply_and_unconfirmed_availability_with_citations() -> None:
    # Critérios 10 e 11 da #25: distingue associação de catálogo, sazonalidade,
    # capacidade estimada, histórico de fornecimento (lotes.csv) e disponibilidade confirmada,
    # citando fontes reais com metadados reconciliados.
    order = OrderToolContract(
        order_id="PED-2026-DIST",
        buyer="Restaurante Raízes",
        delivery_start_date="2026-11-05",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-queijo",
                product_id="prod-queijo",
                product_name="Queijo coalho",
                requested_quantity=Decimal(100),
                allocated_quantity=Decimal(50),
                remaining_balance=Decimal(50),
                unit="kg",
            ),
        ],
    )
    p007 = ProducerCatalogItemContract(
        producer_id="uuid-p007",
        code="P007",
        name="Antônio Carlos Pereira Lima",
        active=True,
        products=[ProductCatalogRef(product_id="prod-queijo", product_name="Queijo coalho")],
    )
    sources = [
        ConsultationSourceItem(
            source_id="src-saz-queijo",
            document_id="doc-saz",
            document_name="sazonalidade.csv",
            reference_label="queijo coalho",
            content="produto=queijo coalho; nov=alta; observacao=Produção contínua.",
        ),
        ConsultationSourceItem(
            source_id="src-cap-p007",
            document_id="doc-cert-p007",
            document_name="cert_organica_antonio_lima_P007.txt",
            reference_label="ORG-PE-2025-005432",
            content="Produtor: Antônio Carlos Pereira Lima (P007)\nQueijo coalho: Produção: até 200 kg/semana",
        ),
        ConsultationSourceItem(
            source_id="src-lot-0108",
            source_kind=SourceKind.LOT_RECORD,
            document_id="doc-lotes",
            document_name="lotes.csv",
            reference_label="LOT-2026-0108",
            content=(
                "lote_id=LOT-2026-0108; data_entrega=2026-10-25; produtor_id=P007; "
                "produtor_nome=Antônio Carlos Pereira Lima; produto=queijo coalho; quantidade_kg=80"
            ),
        ),
    ]

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=[p007],
        sources=sources,
    )
    resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-DIST", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )

    cand = resp.item_suggestions[0].candidates[0]
    assert "não comprova disponibilidade" in cand.catalog_association_note.lower()
    assert cand.seasonality_summary is not None
    assert "nov: alta" in cand.seasonality_summary
    assert cand.estimated_capacity_summary is not None
    assert "200 kg/semana" in cand.estimated_capacity_summary
    assert cand.historical_supply_summary is not None
    assert "LOT-2026-0108" in cand.historical_supply_summary
    assert cand.availability_confirmed is False
    assert any(
        "50 kg" in p and "05/11/2026" in p
        for p in cand.pending_confirmations
    )
    assert set(cand.source_ids) == {"src-saz-queijo", "src-cap-p007", "src-lot-0108"}
    assert len(resp.cited_sources) == 3
    assert {c.document_name for c in resp.cited_sources} == {
        "sazonalidade.csv",
        "cert_organica_antonio_lima_P007.txt",
        "lotes.csv",
    }


@pytest.mark.asyncio
async def test_no_eligible_candidates_and_alternative_product_suggestion_leave_decision_with_staff() -> None:
    # Critérios 12 e 13 da #25:
    # - sem candidato apto -> explica motivo e deixa decisão com o funcionário
    # - ao sugerir produto alternativo -> identifica qual item substituiria e mantém aprovação com o funcionário
    order = OrderToolContract(
        order_id="PED-2026-ALT",
        buyer="Mercado Bom Preço",
        delivery_start_date="2026-11-10",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-umbu",
                product_id="prod-umbu",
                product_name="Umbu",
                requested_quantity=Decimal(50),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(50),
                unit="kg",
            ),
            OrderItemBalanceContract(
                order_item_id="item-banana",
                product_id="prod-banana",
                product_name="Banana prata",
                requested_quantity=Decimal(30),
                allocated_quantity=Decimal(30),
                remaining_balance=Decimal(0),
                unit="kg",
            ),
        ],
    )
    inactive_producer = ProducerCatalogItemContract(
        producer_id="uuid-p015",
        code="P015",
        name="Geraldo Manoel Barbosa",
        active=False,
        products=[ProductCatalogRef(product_id="prod-umbu", product_name="Umbu")],
    )
    sources = [
        ConsultationSourceItem(
            source_id="src-saz-umbu",
            document_id="doc-saz",
            document_name="sazonalidade.csv",
            reference_label="umbu",
            content="produto=umbu; nov=nenhuma; observacao=Safra fev-mai apenas.",
        ),
        ConsultationSourceItem(
            source_id="src-saz-manga",
            document_id="doc-saz",
            document_name="sazonalidade.csv",
            reference_label="manga tommy",
            content="produto=manga tommy; nov=alta; observacao=Safra out-mar.",
        ),
    ]

    model_with_alternative = {
        "order_id": "PED-2026-ALT",
        "buyer": "Mercado Bom Preço",
        "reference_date_used": "2026-10-30",
        "evaluated_delivery_start": "2026-11-10",
        "evaluated_delivery_end": "2026-11-10",
        "exact_delivery_date_used": True,
        "summary": "Sem produtor apto para umbu; alternativa sugerida: manga tommy.",
        "item_suggestions": [
            {
                "order_item_id": "item-umbu",
                "product_id": "prod-umbu",
                "product_name": "Umbu",
                "remaining_balance": 50.0,
                "unit": "kg",
                "balance_status": "disponivel",
                "allocation_message": "Saldo 50 kg.",
                "alternative_suggestions": [
                    {
                        "replaces_order_item_id": "item-errado",
                        "replaces_product_name": "Produto errado",
                        "alternative_product_name": "Manga tommy",
                        "reason": "Umbu sem fornecedor ativo e fora de safra em novembro; manga tommy em alta safra.",
                        "candidate_producers_summary": "P001 (Maria das Graças) e P010 (Raimunda Nonata).",
                        "requires_staff_approval": False,
                        "source_ids": ["src-saz-umbu", "src-saz-manga", "fonte-falsa"],
                    }
                ],
            },
            {
                "order_item_id": "item-banana",
                "product_id": "prod-banana",
                "product_name": "Banana prata",
                "remaining_balance": 0.0,
                "unit": "kg",
                "balance_status": "integralmente_alocado",
                "allocation_message": "Integralmente alocado.",
                "alternative_suggestions": [
                    {
                        "replaces_order_item_id": "item-banana",
                        "replaces_product_name": "Banana prata",
                        "alternative_product_name": "Goiaba",
                        "reason": "Não deveria sugerir alternativa para item já alocado.",
                        "candidate_producers_summary": "P001",
                        "requires_staff_approval": True,
                        "source_ids": ["src-saz-manga"],
                    }
                ],
            },
        ],
    }

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=[inactive_producer],
        sources=sources,
    )
    resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-ALT", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(model_with_alternative),
    )

    by_item = {i.order_item_id: i for i in resp.item_suggestions}
    umbu = by_item["item-umbu"]
    assert umbu.insufficient_data is True
    assert umbu.insufficient_data_reason is not None
    assert umbu.staff_decision_note is not None
    assert "funcionário" in umbu.staff_decision_note.lower()
    assert len(umbu.alternative_suggestions) == 1

    alt = umbu.alternative_suggestions[0]
    assert alt.replaces_order_item_id == "item-umbu"
    assert alt.replaces_product_name == "Umbu"
    assert alt.alternative_product_name == "Manga tommy"
    assert alt.requires_staff_approval is True
    assert alt.source_ids == ["src-saz-umbu", "src-saz-manga"]
    assert "Substituiria 'Umbu' (item-umbu) por 'Manga tommy'" in resp.summary

    # Item já integralmente alocado não recebe alternativas indevidas
    assert by_item["item-banana"].alternative_suggestions == []


@pytest.mark.asyncio
async def test_cancelled_unstructured_and_missing_order_handling_and_producer_response_adapter() -> None:
    prod_id = uuid4()
    producer_resp = ProducerResponse(
        id=uuid4(),
        code="P001",
        name="Maria das Graças Silva Ferreira",
        cpf="831.452.674-90",
        active=True,
        phone="(87) 99812-3456",
        email="maria.graca@email.com",
        address="Sítio Boa Vista",
        municipality="Garanhuns",
        products=[ProductResponse(id=prod_id, name="Goiaba paluma")],
    )
    adapted = ProducerCatalogItemContract.from_producer_response(producer_resp)
    assert adapted.code == "P001"
    assert adapted.active is True
    assert adapted.products[0].product_id == str(prod_id)

    cancelled_order = OrderToolContract(
        order_id="PED-CANCELADO",
        buyer="Comprador X",
        delivery_start_date="2026-11-10",
        cancelled=True,
    )
    unstructured_order = OrderToolContract(
        order_id="PED-LEGADO",
        buyer="Comprador Y",
        delivery_start_date="2026-11-10",
        products_legacy_text="50 kg de goiaba",
        items=[],
    )
    provider = InMemoryProducerSuggestionToolProvider(
        orders=[cancelled_order, unstructured_order],
        producers=[producer_resp],
    )

    cancelled_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-CANCELADO", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert "cancelado" in cancelled_resp.summary.lower()
    assert cancelled_resp.item_suggestions == []

    unstructured_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-LEGADO", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert "itens estruturados" in unstructured_resp.summary.lower()

    missing_resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-INEXISTENTE", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert "não foi encontrado" in missing_resp.summary.lower()


@pytest.mark.asyncio
async def test_hardening_explicit_non_organic_exclusion_multi_producer_capacity_and_word_boundary_matching() -> None:
    # 1. Word-boundary: busca por "Mel" não pode retornar produtor que só fornece "Melado"
    melado_producer = ProducerCatalogItemContract(
        producer_id="uuid-p016",
        code="P016",
        name="Terezinha de Jesus Oliveira",
        active=True,
        products=[ProductCatalogRef(product_id="prod-melado", product_name="Melado")],
    )
    p010_non_organic = ProducerCatalogItemContract(
        producer_id="uuid-p010",
        code="P010",
        name="Raimunda Nonata de Lima",
        active=True,
        products=[ProductCatalogRef(product_id="prod-goiaba", product_name="Goiaba paluma")],
    )
    p020_unverified_organic = ProducerCatalogItemContract(
        producer_id="uuid-p020",
        code="P020",
        name="Produtor Sem Documento Na Base",
        active=True,
        products=[ProductCatalogRef(product_id="prod-goiaba", product_name="Goiaba paluma")],
    )
    p004_alface = ProducerCatalogItemContract(
        producer_id="uuid-p004",
        code="P004",
        name="Ana Lúcia Bezerra da Costa",
        active=True,
        products=[ProductCatalogRef(product_id="prod-alface", product_name="Alface")],
    )
    p009_alface = ProducerCatalogItemContract(
        producer_id="uuid-p009",
        code="P009",
        name="Marcos Vinícius da Rocha",
        active=True,
        products=[ProductCatalogRef(product_id="prod-alface", product_name="Alface")],
    )

    order = OrderToolContract(
        order_id="PED-2026-HARD",
        buyer="Empório Orgânico",
        delivery_start_date="2026-11-05",
        items=[
            OrderItemBalanceContract(
                order_item_id="item-goiaba",
                product_id="prod-goiaba",
                product_name="Goiaba paluma",
                requested_quantity=Decimal(50),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(50),
                unit="kg",
                requires_organic_certification=True,
            ),
            OrderItemBalanceContract(
                order_item_id="item-alface-kg",
                product_id="prod-alface",
                product_name="Alface",
                requested_quantity=Decimal(500),
                allocated_quantity=Decimal(0),
                remaining_balance=Decimal(500),
                unit="kg",
                requires_organic_certification=False,
            ),
        ],
    )

    sources = [
        ConsultationSourceItem(
            source_id="src-prod-p010",
            source_kind=SourceKind.PRODUCER_RECORD,
            document_name="produtores.csv",
            reference_label="P010",
            content="id=P010; nome_completo=Raimunda Nonata de Lima; certificacao_organica=nao; status=ativo",
        ),
        # Trecho curto (<= 20 linhas) contendo capacidades distintas de P004 e P009
        ConsultationSourceItem(
            source_id="src-hortalicas-short",
            document_name="hortalicas.txt",
            content=(
                "P004 - Ana Lúcia Bezerra\n"
                "  Produtos: alface\n"
                "  Capacidade: ~300 kg/semana\n"
                "\n"
                "P009 - Marcos Vinícius da Rocha\n"
                "  Produtos: alface\n"
                "  Capacidade: ~800 kg/semana\n"
            ),
        ),
    ]

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order],
        producers=[
            melado_producer,
            p010_non_organic,
            p020_unverified_organic,
            p004_alface,
            p009_alface,
        ],
        sources=sources,
    )

    # "Mel" não casa com "Melado"
    assert provider.list_producers_by_product(product_name="Mel") == []

    resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id="PED-2026-HARD", reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )

    by_item = {i.order_item_id: i for i in resp.item_suggestions}

    # P010 (explicitamente nao organico em produtores.csv) é excluído; P020 (sem documento) depende de confirmação
    goiaba = by_item["item-goiaba"]
    assert [e.producer_code for e in goiaba.excluded_producers] == ["P010"]
    assert [c.producer_code for c in goiaba.candidates] == ["P020"]
    assert goiaba.candidates[0].proof_status == CandidateProofStatus.NEEDS_CONFIRMATION

    # Em hortalicas.txt (<=20 linhas com dois produtores), P004 recebe 300 kg/semana (acima da capacidade para 500 kg)
    # e P009 recebe 800 kg/semana (compatível para 500 kg)
    alface_cands = {c.producer_code: c for c in by_item["item-alface-kg"].candidates}
    assert (
        alface_cands["P004"].capacity_comparison_status
        == CapacityComparisonStatus.ABOVE_ESTIMATED_CAPACITY
    )
    assert (
        alface_cands["P009"].capacity_comparison_status
        == CapacityComparisonStatus.COMPATIBLE
    )

    # Round-trip de revalidação do schema mantém integridade exata
    revalidated_dict = ProducerSuggestionResponse.model_validate(resp.model_dump())
    revalidated_json = ProducerSuggestionResponse.model_validate_json(
        resp.model_dump_json()
    )
    assert revalidated_dict == resp
    assert revalidated_json == resp


@pytest.mark.asyncio
async def test_from_order_response_and_producer_response_alignment_with_issue_36_and_23() -> None:
    # Valida compatibilidade direta com os schemas reais da aplicação mesclados na main:
    # - OrderResponse / OrderItemResponse (#36 / PR #41)
    # - ProducerResponse / ProductResponse (#23)
    # - ConsultationSourceItem com record_id e record_fields (#40 / PR #47)
    from datetime import date
    from uuid import uuid4

    from api.schemas.order import OrderItemResponse, OrderResponse
    from api.schemas.producer import ProducerResponse
    from api.schemas.product import ProductResponse

    order_uuid = uuid4()
    item_uuid = uuid4()
    prod_uuid = uuid4()
    producer_uuid = uuid4()

    product_schema = ProductResponse(id=prod_uuid, name="Queijo coalho")
    order_schema = OrderResponse(
        id=order_uuid,
        version=2,
        session_id=None,
        cancelled=False,
        buyer="Mercado Bom Preço",
        conditions="Entrega pela manhã",
        delivery_start_date=date(2026, 11, 4),
        delivery_end_date=date(2026, 11, 8),
        products="100 kg de Queijo coalho",
        items=[
            OrderItemResponse(
                id=item_uuid,
                product_id=prod_uuid,
                quantity=Decimal("100.000"),
                unit="kg",
                product=product_schema,
            )
        ],
    )
    producer_schema = ProducerResponse(
        id=producer_uuid,
        code="P007",
        name="Antônio Carlos Pereira Lima",
        cpf="12345678901",
        active=True,
        phone=None,
        email=None,
        address=None,
        municipality="Garanhuns",
        products=[product_schema],
    )

    order_contract = OrderToolContract.from_order_response(
        order_schema,
        item_balances={
            str(item_uuid): {
                "allocated_quantity": Decimal(50),
                "remaining_balance": Decimal(50),
            }
        },
    )
    assert order_contract.order_id == str(order_uuid)
    assert order_contract.order_version == 2
    assert order_contract.needs_item_structuring is False
    assert len(order_contract.items) == 1
    assert order_contract.items[0].remaining_balance == Decimal(50)

    provider = InMemoryProducerSuggestionToolProvider(
        orders=[order_contract],
        producers=[producer_schema],
        sources=[
            ConsultationSourceItem(
                source_id="src-lot-36",
                source_kind=SourceKind.LOT_RECORD,
                document_id="doc-lotes",
                document_name="lotes.csv",
                reference_label="LOT-2026-0108",
                record_id="LOT-2026-0108",
                record_fields={
                    "lote_id": "LOT-2026-0108",
                    "produtor_id": "P007",
                    "produto": "queijo coalho",
                    "quantidade_kg": "80",
                },
                content="lote_id=LOT-2026-0108; produtor_id=P007; produto=queijo coalho; quantidade_kg=80",
            )
        ],
    )

    resp = await suggest_producers_for_order(
        ProducerSuggestionInput(order_id=str(order_uuid), reference_date="2026-10-30"),
        tool_provider=provider,
        runner=FakeSuggestionRunner(),
    )
    assert resp.order_id == str(order_uuid)
    assert resp.evaluated_delivery_start == "2026-11-04"
    assert resp.evaluated_delivery_end == "2026-11-08"
    assert len(resp.item_suggestions) == 1
    item_res = resp.item_suggestions[0]
    assert item_res.order_item_id == str(item_uuid)
    assert item_res.remaining_balance == 50.0
    assert [c.producer_code for c in item_res.candidates] == ["P007"]
    assert item_res.candidates[0].historical_supply_summary is not None
    assert "LOT-2026-0108" in item_res.candidates[0].historical_supply_summary
