from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types
from pydantic import ValidationError

from api.agents.consultation import (
    CONSULTATION_OUTPUT_KEY,
    ConsultationInput,
    ConsultationResponse,
    ConsultationSourceItem,
    SourceKind,
    answer_document_consultation,
    build_consultation_instruction,
    consultation_agent,
    create_consultation_agent,
    format_consultation_prompt,
    reconcile_consultation_sources,
)


class FakeSessionService:
    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}

    async def create_session(self, app_name: str, user_id: str) -> SimpleNamespace:
        session = SimpleNamespace(
            id="session-consult-1",
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


class FakeConsultationRunner:
    def __init__(
        self,
        response_payload: dict[str, Any] | ConsultationResponse,
        *,
        store_in_state: bool = True,
    ) -> None:
        self.app_name = "sabor_da_terra_consultation"
        self.session_service = FakeSessionService()
        self._response_payload = response_payload
        self._store_in_state = store_in_state
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

        if isinstance(self._response_payload, ConsultationResponse):
            json_text = self._response_payload.model_dump_json()
            state_val: Any = self._response_payload.model_dump()
        else:
            import json

            json_text = json.dumps(self._response_payload, ensure_ascii=False)
            state_val = self._response_payload

        if self._store_in_state:
            session.state[CONSULTATION_OUTPUT_KEY] = state_val

        yield SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json_text)],
            ),
            is_final_response=lambda: True,
        )


def test_create_consultation_agent_configures_adk_agent() -> None:
    agent = create_consultation_agent(model="gemini-3.5-flash")
    assert agent.name == "consultation_agent"
    assert agent.output_schema is ConsultationResponse
    assert agent.output_key == CONSULTATION_OUTPUT_KEY
    assert consultation_agent.name == "consultation_agent"
    instruction = build_consultation_instruction(SimpleNamespace())
    assert "RF05" in instruction
    assert "RF06" in instruction
    assert "RF07" in instruction


def test_consultation_input_uses_current_pernambuco_date_when_omitted() -> None:
    payload = ConsultationInput(question="Quais produtores têm mel orgânico?")
    assert isinstance(payload.resolved_reference_date, date)


def test_consultation_input_rejects_blank_question() -> None:
    with pytest.raises(ValidationError, match="question must not be blank"):
        ConsultationInput(question="   ")


def test_format_consultation_prompt_includes_sources_and_reference_date() -> None:
    payload = ConsultationInput(
        question="Qual a origem do lote LOT-2026-0094?",
        reference_date="2026-11-11",
        sources=[
            ConsultationSourceItem(
                source_id="chunk-lot-0094",
                source_kind=SourceKind.LOT_RECORD,
                document_id="doc-lotes-csv",
                document_name="lotes.csv",
                reference_label="LOT-2026-0094",
                content="LOT-2026-0094 | P004 Ana Lúcia Bezerra | alface | 300 unidades",
            )
        ],
    )
    prompt = format_consultation_prompt(payload)
    assert "data_referencia: 2026-11-11 (11/11/2026)" in prompt
    assert 'id="chunk-lot-0094"' in prompt
    assert 'documento="lotes.csv"' in prompt
    assert 'referencia="LOT-2026-0094"' in prompt
    assert "<pergunta_funcionario>\nQual a origem do lote LOT-2026-0094?\n</pergunta_funcionario>" in prompt


def test_reconcile_consultation_sources_filters_unknown_ids_and_fills_metadata() -> None:
    payload = ConsultationInput(
        question="Quem fornece mel orgânico?",
        reference_date="2026-10-30",
        sources=[
            ConsultationSourceItem(
                source_id="chunk-cert-p002",
                document_id="doc-uuid-p002",
                document_name="cert_organica_jose_santos_P002.txt",
                reference_label="ORG-PE-2025-003198",
                content="Certificado ORG-PE-2025-003198 válido até 20/03/2027 para mel silvestre.",
            )
        ],
    )
    raw = ConsultationResponse(
        answer="José Antônio (P002) possui certificação vigente até 20/03/2027.",
        reference_date_used="2026-10-30",
        source_ids=["chunk-cert-p002", "hallucinated-id-999"],
        cited_sources=[],
    )

    reconciled = reconcile_consultation_sources(raw, payload)
    assert reconciled.source_ids == ["chunk-cert-p002"]
    assert len(reconciled.cited_sources) == 1
    assert reconciled.cited_sources[0].document_id == "doc-uuid-p002"
    assert (
        reconciled.cited_sources[0].document_name
        == "cert_organica_jose_santos_P002.txt"
    )
    assert reconciled.cited_sources[0].reference_label == "ORG-PE-2025-003198"


@pytest.mark.asyncio
async def test_consultation_reconciliation_overrides_divergent_metadata_and_keeps_missing_values_none() -> None:
    # Critério 1 da #37 (Consulta): saída simulada com source_id válido e document_id ou
    # referência divergentes usa os metadados da fonte recuperada e mantém None quando a fonte não informa
    payload = ConsultationInput(
        question="Quais informações constam nas duas fontes recuperadas?",
        reference_date="2026-10-30",
        sources=[
            ConsultationSourceItem(
                source_id="src-with-meta",
                document_id="doc-real-001",
                document_name="cert_organica_jose_santos_P002.txt",
                reference_label="ORG-PE-2025-003198",
                content="Certificado válido até 20/03/2027.",
            ),
            ConsultationSourceItem(
                source_id="src-without-optional-meta",
                document_id=None,
                document_name="anotacao_operacional.txt",
                reference_label=None,
                content="Observação interna sem identificador de registro.",
            ),
        ],
    )
    simulated_output = {
        "answer": "Resumo com base nas fontes recuperadas em 30/10/2026.",
        "reference_date_used": "2026-10-30",
        "source_ids": ["src-with-meta", "src-without-optional-meta"],
        "cited_sources": [
            {
                "source_id": "src-with-meta",
                "document_id": "doc-divergente-999",
                "document_name": "nome_divergente.txt",
                "reference_label": "REF-DIVERGENTE-999",
                "supporting_excerpt": "Trecho real 1.",
            },
            {
                "source_id": "src-without-optional-meta",
                "document_id": "doc-inventado-888",
                "document_name": "outro_nome.txt",
                "reference_label": "REF-INVENTADA-888",
                "supporting_excerpt": "Trecho real 2.",
            },
        ],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }

    runner = FakeConsultationRunner(simulated_output)
    result = await answer_document_consultation(payload, runner=runner)

    assert result.source_ids == ["src-with-meta", "src-without-optional-meta"]
    assert len(result.cited_sources) == 2

    first_cited = result.cited_sources[0]
    assert first_cited.source_id == "src-with-meta"
    assert first_cited.document_id == "doc-real-001"
    assert first_cited.document_name == "cert_organica_jose_santos_P002.txt"
    assert first_cited.reference_label == "ORG-PE-2025-003198"
    assert first_cited.supporting_excerpt == "Trecho real 1."

    second_cited = result.cited_sources[1]
    assert second_cited.source_id == "src-without-optional-meta"
    assert second_cited.document_id is None
    assert second_cited.document_name == "anotacao_operacional.txt"
    assert second_cited.reference_label is None
    assert second_cited.supporting_excerpt == "Trecho real 2."


@pytest.mark.asyncio
async def test_consultation_verifies_organic_certification_validity_and_divergence() -> None:
    # Critérios 1, 3 e 4 da #14: verifica cobertura e vigência na data de referência
    # (P002 vigente até 20/03/2027; P008 vencida em 30/09/2026 e divergente com LOT-2026-0104)
    payload = ConsultationInput(
        question="Quais produtores possuem certificação orgânica vigente para mel silvestre?",
        reference_date="2026-10-30",
        sources=[
            ConsultationSourceItem(
                source_id="chunk-cert-p002",
                document_id="doc-cert-p002",
                document_name="cert_organica_jose_santos_P002.txt",
                reference_label="ORG-PE-2025-003198",
                content=(
                    "Certificado Nº ORG-PE-2025-003198. Produtor: José Antônio dos Santos (P002). "
                    "Data de Validade: 20/03/2027. Produtos certificados: Mel silvestre, "
                    "Mel de abelha jandaíra, Própolis verde."
                ),
            ),
            ConsultationSourceItem(
                source_id="chunk-cert-p008",
                document_id="doc-cert-p008",
                document_name="cert_organica_josefa_souza_P008.txt",
                reference_label="ORG-PE-2024-003876",
                content=(
                    "Certificado Nº ORG-PE-2024-003876. Produtora: Josefa Alves de Souza (P008). "
                    "Data de Validade: 30/09/2026 *** VENCIDA ***. Produtos que eram certificados: "
                    "Mel silvestre, Geleia de frutas, Doce de goiaba. Até a conclusão da renovação, "
                    "os produtos NÃO podem ser comercializados como orgânicos."
                ),
            ),
            ConsultationSourceItem(
                source_id="rec-lot-0104",
                source_kind=SourceKind.LOT_RECORD,
                document_id="doc-lotes",
                document_name="lotes.csv",
                reference_label="LOT-2026-0104",
                content=(
                    "lote_id=LOT-2026-0104, data_entrega=2026-10-01, produtor=P008 Josefa Alves de Souza, "
                    "produto=mel silvestre, quantidade=10 kg, observacao=Certificação orgânica anexa"
                ),
            ),
        ],
    )

    simulated_output = {
        "answer": (
            "Considerando a data de referência 30/10/2026:\n"
            "- José Antônio dos Santos (P002) possui certificação orgânica vigente "
            "(ORG-PE-2025-003198, válida até 20/03/2027) cobrindo mel silvestre "
            "[cert_organica_jose_santos_P002.txt].\n"
            "- Josefa Alves de Souza (P008) está com o certificado ORG-PE-2024-003876 "
            "vencido desde 30/09/2026, não podendo comercializar mel silvestre como "
            "orgânico até a conclusão da renovação [cert_organica_josefa_souza_P008.txt]. "
            "Há divergência com o registro LOT-2026-0104 em lotes.csv, entregue em "
            "01/10/2026 com a observação 'Certificação orgânica anexa' após o vencimento."
        ),
        "reference_date_used": "2026-10-30",
        "source_ids": ["chunk-cert-p002", "chunk-cert-p008", "rec-lot-0104"],
        "cited_sources": [
            {
                "source_id": "chunk-cert-p002",
                "document_name": "cert_organica_jose_santos_P002.txt",
                "reference_label": "ORG-PE-2025-003198",
                "supporting_excerpt": "Validade 20/03/2027 cobrindo mel silvestre.",
            },
            {
                "source_id": "chunk-cert-p008",
                "document_name": "cert_organica_josefa_souza_P008.txt",
                "reference_label": "ORG-PE-2024-003876",
                "supporting_excerpt": "Certificado expirado em 30/09/2026.",
            },
            {
                "source_id": "rec-lot-0104",
                "document_name": "lotes.csv",
                "reference_label": "LOT-2026-0104",
                "supporting_excerpt": "Entrega em 01/10/2026 com observação de certificação orgânica anexa.",
            },
        ],
        "gaps_and_divergences": [
            {
                "kind": "certificacao_vencida_ou_incompativel",
                "description": (
                    "O certificado ORG-PE-2024-003876 da produtora P008 (Josefa Alves de Souza) "
                    "venceu em 30/09/2026 e está inapto na data de referência 30/10/2026."
                ),
                "source_ids": ["chunk-cert-p008"],
            },
            {
                "kind": "divergencia",
                "description": (
                    "O lote LOT-2026-0104 registra entrega de mel silvestre pela produtora P008 "
                    "em 01/10/2026 com 'Certificação orgânica anexa', mas o certificado "
                    "ORG-PE-2024-003876 expirou em 30/09/2026."
                ),
                "source_ids": ["chunk-cert-p008", "rec-lot-0104"],
            },
        ],
        "has_sufficient_data": True,
    }

    runner = FakeConsultationRunner(simulated_output)
    result = await answer_document_consultation(payload, runner=runner)

    assert result.reference_date == date(2026, 10, 30)
    assert result.source_ids == ["chunk-cert-p002", "chunk-cert-p008", "rec-lot-0104"]
    assert {g.kind for g in result.gaps_and_divergences} == {
        "certificacao_vencida_ou_incompativel",
        "divergencia",
    }
    assert result.has_sufficient_data is True


@pytest.mark.asyncio
async def test_consultation_traces_lot_0094_and_flags_ambiguous_unit_in_lot_0099() -> None:
    # Critérios 2, 3 e 4 da #14 + US06: LOT-2026-0094 informa 300 unidades de alface
    # e LOT-2026-0099 indica que "40 maços (kg)" tem unidade ambígua e fica fora dos totais
    payload = ConsultationInput(
        question="Qual a rastreabilidade dos lotes LOT-2026-0094 e LOT-2026-0099?",
        reference_date="2026-11-11",
        sources=[
            ConsultationSourceItem(
                source_id="rec-lot-0094",
                source_kind=SourceKind.LOT_RECORD,
                document_id="doc-lotes",
                document_name="lotes.csv",
                reference_label="LOT-2026-0094",
                content=(
                    "lote_id=LOT-2026-0094, data_colheita=2026-09-06, data_entrega=2026-09-08, "
                    "produtor_id=P004, produtor_nome=Ana Lúcia Bezerra da Costa, produto=alface, "
                    "quantidade_kg=300, comprador=Prefeitura de Garanhuns - PNAE, "
                    "pedido_id=PED-2026-SEP-008, observacao=300 unidades"
                ),
            ),
            ConsultationSourceItem(
                source_id="rec-lot-0099",
                source_kind=SourceKind.LOT_RECORD,
                document_id="doc-lotes",
                document_name="lotes.csv",
                reference_label="LOT-2026-0099",
                content=(
                    "lote_id=LOT-2026-0099, data_colheita=2026-09-15, data_entrega=2026-09-15, "
                    "produtor_id=P009, produtor_nome=Marcos Vinícius da Rocha, produto=couve, "
                    "quantidade_kg=40, comprador=Hospital São Francisco, "
                    "pedido_id=PED-2026-SEP-015, observacao=40 maços (kg)"
                ),
            ),
        ],
    )

    simulated_output = {
        "answer": (
            "Na data de referência 11/11/2026, os registros em lotes.csv informam:\n"
            "- LOT-2026-0094: 300 unidades de alface, fornecidas por Ana Lúcia Bezerra "
            "da Costa (P004), colheita em 06/09/2026 e entrega em 08/09/2026 para "
            "Prefeitura de Garanhuns - PNAE (pedido PED-2026-SEP-008).\n"
            "- LOT-2026-0099: couve fornecida por Marcos Vinícius da Rocha (P009) em "
            "15/09/2026 para o Hospital São Francisco (PED-2026-SEP-015), porém a "
            "descrição '40 maços (kg)' possui unidade ambígua (maços vs. kg) e deve "
            "permanecer fora dos totais até esclarecimento."
        ),
        "reference_date_used": "2026-11-11",
        "source_ids": ["rec-lot-0094", "rec-lot-0099"],
        "cited_sources": [],
        "gaps_and_divergences": [
            {
                "kind": "unidade_ambigua",
                "description": (
                    "O registro LOT-2026-0099 apresenta '40 maços (kg)', com conflito "
                    "entre maços e quilogramas; quantidade mantida fora de somas e conversões."
                ),
                "source_ids": ["rec-lot-0099"],
            }
        ],
        "has_sufficient_data": True,
    }

    runner = FakeConsultationRunner(simulated_output, store_in_state=False)
    result = await answer_document_consultation(payload, runner=runner)

    assert "300 unidades" in result.answer
    assert "40 maços (kg)" in result.answer
    assert result.source_ids == ["rec-lot-0094", "rec-lot-0099"]
    assert len(result.cited_sources) == 2
    assert result.cited_sources[0].reference_label == "LOT-2026-0094"
    assert result.gaps_and_divergences[0].kind == "unidade_ambigua"


@pytest.mark.asyncio
async def test_consultation_handles_empty_sources_without_inventing() -> None:
    # Critério 2 da #37 (Consulta) + RF07: com lista de fontes vazia, retorna mensagem
    # definida pelo código, indica dados insuficientes, sem citações e sem exibir conclusão simulada do modelo
    from api.agents.consultation.reconciliation import (
        INSUFFICIENT_SOURCES_MESSAGE,
        build_insufficient_sources_message,
    )

    payload = ConsultationInput(
        question="Existe certificado fitossanitário internacional para exportação de maracujá?",
        reference_date="2026-10-30",
        sources=[],
    )

    simulated_output = {
        "answer": (
            "CONCLUSAO_SIMULADA_DO_MODELO: Sim, a cooperativa possui o certificado "
            "INT-MARACUJA-999 válido até 2028 para exportação."
        ),
        "reference_date_used": "2026-10-30",
        "source_ids": ["fonte-inexistente"],
        "cited_sources": [
            {
                "source_id": "fonte-inexistente",
                "document_name": "cert_falso.txt",
                "reference_label": "INT-MARACUJA-999",
            }
        ],
        "gaps_and_divergences": [],
        "has_sufficient_data": True,
    }

    runner = FakeConsultationRunner(simulated_output)
    result = await answer_document_consultation(payload, runner=runner)

    assert result.has_sufficient_data is False
    assert result.source_ids == []
    assert result.cited_sources == []
    assert result.answer == build_insufficient_sources_message("2026-10-30")
    assert INSUFFICIENT_SOURCES_MESSAGE in result.answer
    assert "CONCLUSAO_SIMULADA_DO_MODELO" not in result.answer
    assert "INT-MARACUJA-999" not in result.answer
    assert any(g.kind == "lacuna" for g in result.gaps_and_divergences)


def test_consultation_schema_is_compatible_with_google_genai_transformer() -> None:
    from google.genai._transformers import t_schema

    schema = t_schema(None, ConsultationResponse)
    assert schema is not None


def test_consultation_schemas_public_and_split_module_imports() -> None:
    from api.agents.consultation import reconciliation as recon_module
    from api.agents.consultation import schemas as public_schemas
    from api.agents.consultation.schemas.input import (
        ConsultationInput as InputFromModule,
    )
    from api.agents.consultation.schemas.input import (
        ConsultationSourceItem as SourceItemFromModule,
    )
    from api.agents.consultation.schemas.input import (
        SourceKind as SourceKindFromModule,
    )
    from api.agents.consultation.schemas.response import (
        CitedSource as CitedSourceFromModule,
    )
    from api.agents.consultation.schemas.response import (
        ConsultationGapOrDivergence as GapFromModule,
    )
    from api.agents.consultation.schemas.response import (
        ConsultationResponse as ResponseFromModule,
    )

    assert public_schemas.ConsultationInput is InputFromModule
    assert public_schemas.ConsultationSourceItem is SourceItemFromModule
    assert public_schemas.SourceKind is SourceKindFromModule
    assert public_schemas.CitedSource is CitedSourceFromModule
    assert public_schemas.ConsultationGapOrDivergence is GapFromModule
    assert public_schemas.ConsultationResponse is ResponseFromModule
    assert (
        public_schemas.reconcile_consultation_sources
        is recon_module.reconcile_consultation_sources
    )
