import csv
import json
from pathlib import Path
from uuid import uuid4

import pytest

from api.agents.agent import orchestrate_request
from api.agents.consultation.schemas import ConsultationSourceItem
from api.agents.schemas import OrchestratorRequest
from api.agents.triage.enrichment import enrich_triage_analysis
from api.agents.triage.schemas import TriageAnalysis
from api.schemas.agent_integration import (
    DocumentRetrievalContext,
    InMemoryDocumentSourceProvider,
)
from api.services.agent_integration import convert_orchestrator_response
from tests.unit.agents.test_orchestrator import FakeSpecialistRunner

DATA = Path(__file__).resolve().parents[3] / "data"
pytestmark = pytest.mark.asyncio


def analysis(
    product="Mel silvestre",
    *,
    quantity=20,
    unit="kg",
    start="2026-11-04",
    end="2026-11-08",
    **extra,
):
    return TriageAnalysis.model_validate(
        {
            "summary": "Pedido para triagem.",
            "request_type": "pedido",
            "urgency": "normal",
            "urgency_reason": "Prazo informado.",
            "received_date_reference": "2026-10-28",
            "extracted_data": {
                "buyer_name": "Prefeitura de Garanhuns - PNAE",
                "delivery_date_start": start,
                "delivery_date_end": end,
                "items": [{"product": product, "quantity": quantity, "unit": unit}],
                **extra,
            },
        }
    )


def source(name, content, **fields):
    return ConsultationSourceItem(
        source_id=uuid4(), document_name=name, content=content, **fields
    )


def runner(*evidence):
    return FakeSpecialistRunner("evidence", {"evidence": list(evidence)})


def season(product):
    with (DATA / "sazonalidade.csv").open(encoding="utf-8", newline="") as stream:
        row = next(row for row in csv.DictReader(stream) if row["produto"] == product)
    return source(
        "sazonalidade.csv", json.dumps(row, ensure_ascii=False), record_fields=row
    )


async def test_ped_2026_004_uses_contract_and_checks_dap_and_honey_certificate():
    received = next(
        entry
        for entry in json.loads((DATA / "pedidos.json").read_text(encoding="utf-8"))
        if entry["id"] == "PED-2026-004"
    )
    contract = source(
        "contrato_pnae_garanhuns.txt",
        (DATA / "contratos/contrato_pnae_garanhuns.txt").read_text(encoding="utf-8"),
    )
    certificate = source(
        "cert_organica_jose_santos_P002.txt",
        (DATA / "certificacoes/cert_organica_jose_santos_P002.txt").read_text(
            encoding="utf-8"
        ),
    )
    original = analysis(contract_reference="Contrato nº 045/2026-PNAE")
    source_provider = InMemoryDocumentSourceProvider(
        sources=[contract, certificate, season("mel silvestre")]
    )
    context = DocumentRetrievalContext(
        session_id=uuid4(), query_text=received["mensagem_original"], flow="triage"
    )
    retrieved = await source_provider.retrieve_sources(context)
    request = OrchestratorRequest(
        session_id=context.session_id,
        flow=context.flow,
        message_text=context.query_text,
        received_at=received["data_recebimento"],
        sources=retrieved.sources,
    )
    certificate_excerpt = certificate.content.split("Data de Emissão:", 1)[1].split(
        "     - Apiários:", 1
    )[0]
    documentary_runner = runner(
        {
            "kind": "dap_caf",
            "source_id": contract.source_id,
            "contract_reference": "045/2026-PNAE",
            "excerpt": "Todos os produtores devem possuir DAP ou CAF vigente",
        },
        {
            "kind": "contract",
            "source_id": contract.source_id,
            "contract_reference": "045/2026-PNAE",
            "excerpt": "Notas fiscais individuais por produtor",
            "description": "O contrato exige notas fiscais individuais por produtor.",
        },
        {
            "kind": "certificate",
            "source_id": certificate.source_id,
            "excerpt": certificate_excerpt,
            "product": "Mel silvestre",
            "valid_from": "2025-03-20",
            "valid_until": "2027-03-20",
        },
    )
    response = await orchestrate_request(
        request,
        triage_runner=FakeSpecialistRunner(
            "triage_analysis", original.model_dump(mode="json")
        ),
        triage_enrichment_runner=documentary_runner,
    )
    result = response.result
    assert isinstance(result, TriageAnalysis)
    assert result.extracted_data == original.extracted_data
    assert result.request_type == original.request_type
    assert result.urgency == original.urgency
    assert result.urgency_reason == original.urgency_reason
    assert result.received_date == original.received_date
    assert received["id"] == "PED-2026-004"
    assert "SDR/PE-2018-0031456" in documentary_runner.received_prompts[0]
    findings = result.document_enrichment.findings
    dap = next(f for f in findings if "DAP ou CAF" in f.description)
    assert dap.needs_follow_up and dap.source_ids == [contract.source_id]
    assert "número de inscrição é insuficiente" in dap.description
    assert any("notas fiscais individuais" in f.description for f in findings)
    organic = next(f for f in findings if f.kind == "certificacao")
    assert not organic.needs_follow_up
    assert organic.source_ids == [certificate.source_id]
    prepared = convert_orchestrator_response(response, original_request=request)
    assert set(map(str, prepared.citation_chunk_ids)) == {
        contract.source_id,
        certificate.source_id,
    }
    assert "Verificação documental e operacional" in prepared.content
    assert "DAP ou CAF vigente" in prepared.content


@pytest.mark.parametrize(
    ("unit", "quantity", "end", "expected"),
    [
        ("g", 501_000, "2026-07-07", "supera a capacidade"),
        ("kg", 400, "2026-07-07", "Confirmar disponibilidade atual"),
        ("potes", 501, "2026-07-07", "unidades incompatíveis"),
        ("kg", 501, "2026-07-05", "período da entrega não é comparável"),
    ],
)
async def test_season_and_capacity_apply_only_to_comparable_periods_and_units(
    unit, quantity, end, expected
):
    extracted = analysis(
        "Goiaba paluma",
        unit=unit,
        quantity=quantity,
        start="2027-07-01",
        end=end.replace("2026", "2027"),
    )
    record = season("goiaba paluma")
    capacity = source(
        "capacidade_estimada.txt",
        "Goiaba paluma, cooperativa: capacidade estimada de 500 kg/semana.",
    )
    history = source("lotes.csv", "Goiaba paluma: 80 kg entregues em junho.")
    output = await enrich_triage_analysis(
        extracted,
        [record, capacity, history],
        runner=runner(
            {
                "kind": "capacity",
                "source_id": capacity.source_id,
                "excerpt": capacity.content,
                "product": "Goiaba paluma",
                "scope": "cooperativa",
                "amount": 500,
                "unit": "kg",
                "period": "semana",
            },
            {
                "kind": "history",
                "source_id": history.source_id,
                "excerpt": history.content,
                "description": "Goiaba paluma: 80 kg entregues em junho.",
            },
        ),
    )
    findings = output.document_enrichment.findings
    assert any(
        f.kind == "sazonalidade"
        and f.source_ids == [record.source_id]
        and "jul" in f.description
        for f in findings
    )
    estimate = next(f for f in findings if f.kind == "capacidade_estimada")
    assert expected in estimate.description and estimate.source_ids == [
        capacity.source_id
    ]
    assert estimate.needs_follow_up
    assert any(
        f.kind == "historico" and f.source_ids == [history.source_id] for f in findings
    )


async def test_expires_during_delivery_and_missing_coverage_are_pending():
    extracted = analysis(
        items=[
            {
                "product": "Mel silvestre",
                "quantity": 20,
                "unit": "kg",
                "condition_text": "orgânico",
            },
            {
                "product": "Goiaba",
                "quantity": 5,
                "unit": "kg",
                "condition_text": "certificação orgânica",
            },
        ]
    )
    certificate = source(
        "certificado.txt",
        "Cobertura: Mel silvestre. Vigência: 01/02/2026 a 06/11/2026.",
    )
    output = await enrich_triage_analysis(
        extracted,
        [certificate],
        runner=runner(
            {
                "kind": "certificate",
                "source_id": certificate.source_id,
                "excerpt": certificate.content,
                "product": "Mel silvestre",
                "valid_from": "2026-02-01",
                "valid_until": "2026-11-06",
            },
            {
                "kind": "certificate",
                "source_id": certificate.source_id,
                "excerpt": certificate.content,
                "product": "Goiaba",
                "valid_from": "2026-02-01",
                "valid_until": "2026-11-06",
            },
        ),
    )
    findings = output.document_enrichment.findings
    assert any(
        f.needs_follow_up and "não cobre todo" in f.description for f in findings
    )
    assert any(
        "Goiaba: falta comprovar cobertura" in f.description and not f.source_ids
        for f in findings
    )


async def test_conflicting_seasonal_records_and_invalid_citations():
    extracted = analysis(contract_reference="045/2026-PNAE")
    first = season("mel silvestre")
    second = source(
        "sazonalidade.csv",
        "Mel silvestre: novembro baixo.",
        record_fields={"produto": "mel silvestre", "nov": "baixa"},
    )
    result = await enrich_triage_analysis(
        extracted,
        [first, second],
        runner=runner(
            {
                "kind": "contract",
                "source_id": str(uuid4()),
                "excerpt": first.content,
                "description": "Sem fonte",
            },
            {
                "kind": "document",
                "source_id": first.source_id,
                "excerpt": "Trecho inventado",
                "description": "Sem trecho",
            },
        ),
    )
    findings = result.document_enrichment.findings
    assert result.requires_clarification
    assert result.document_enrichment.source_ids == [first.source_id, second.source_id]
    assert any(f.kind == "divergencia" for f in findings)
    assert any("Localizar as cláusulas" in f.description for f in findings)
    assert not any(
        "Sem fonte" in f.description or "Sem trecho" in f.description for f in findings
    )


async def test_no_documents_keeps_original_extraction_and_signals_gap():
    original = analysis()
    result = await enrich_triage_analysis(original, [])
    assert result.extracted_data == original.extracted_data
    assert result.urgency == original.urgency
    assert result.requires_clarification
    assert result.document_enrichment.source_ids == []
    assert any(
        "Nenhuma fonte recuperada" in f.description
        for f in result.document_enrichment.findings
    )
