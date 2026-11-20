import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from api.agents.consultation.financial import calculate_producer_financial_summary
from api.agents.consultation.schemas import ConsultationSourceItem
from api.load import import_facepe
from api.models import Lot, Producer, Product
from api.repositories.lot import LotRepository
from api.schemas.agent_integration import (
    DocumentRetrievalContext,
    InMemoryDocumentSourceProvider,
)
from api.schemas.order import OrderCreate
from api.services.producer_summary import ProducerSummaryService
from tests.integration.services.test_order_allocations import order_service

DATA = Path(__file__).resolve().parents[3] / "data"
pytestmark = pytest.mark.asyncio


def _rows(filename):
    with (DATA / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sources(filename, rows, key):
    return [
        ConsultationSourceItem(
            source_id=str(uuid4()),
            document_id=str(uuid4()),
            document_name=filename,
            record_id=row[key],
            record_fields=row,
            content=f"Registro {row[key]}",
        )
        for row in rows
    ]


async def _prepare(db_session):
    lots = _rows("lotes.csv")
    await import_facepe(db_session, _rows("produtores.csv"), lots)
    historical = _sources("lotes.csv", lots, "lote_id")
    financial = _sources("financeiro.csv", _rows("financeiro.csv"), "id_transacao")
    provider = InMemoryDocumentSourceProvider(
        sources=historical, financial_records=financial
    )
    return (
        ProducerSummaryService(LotRepository(db_session), provider),
        provider,
        financial,
    )


async def test_facepe_summary_combines_original_financial_calculation_with_delivery_records(
    db_session,
):
    service, provider, records = await _prepare(db_session)
    session_id = uuid4()
    reference = date(2026, 10, 1)
    response = await service.answer_producer_summary(
        "p004",
        session_id=session_id,
        reference_date=reference,
        period="2026-09",
    )
    expected = calculate_producer_financial_summary(
        "P004",
        reference_date=reference,
        period="2026-09",
        financial_records=records,
    )
    assert response.financial == expected
    assert response.producer_code == "P004"
    assert response.producer_name in response.answer
    assert response.period_start == date(2026, 9, 1)
    assert response.period_end == date(2026, 9, 30)
    assert response.reference_date == reference
    assert set(expected.all_source_ids) <= set(response.source_ids)
    assert expected.sales_in_period.formatted_total in response.answer
    assert "Pagamentos registrados" in response.answer
    assert "Pendências" in response.answer
    assert [
        (row.product, row.quantity, row.unit, row.delivery_date)
        for row in response.planned_supplies.supplies
    ] == [
        ("alface", Decimal(300), "un", date(2026, 9, 8)),
        ("coentro", Decimal(150), "maços", date(2026, 9, 8)),
    ]
    assert {
        citation.reference_label
        for citation in response.cited_sources
        if citation.document_name == "lotes.csv"
    } == {
        "LOT-2026-0094",
        "LOT-2026-0095",
    }
    assert "300 unidades" in response.answer and "150 maços" in response.answer
    assert "08/09/2026" in response.answer
    context = provider.received_contexts[0]
    assert (
        context.session_id,
        context.producer_id,
        context.period_start,
        context.period_end,
    ) == (
        session_id,
        "P004",
        response.period_start,
        response.period_end,
    )

    delivery = await service.answer_producer_summary(
        "P004",
        session_id=session_id,
        reference_date=reference,
        period="2026-09-08",
    )
    harvest = await service.answer_producer_summary(
        "P004",
        session_id=session_id,
        reference_date=reference,
        period="2026-09-06",
    )
    assert len(delivery.planned_supplies.supplies) == 2
    assert not harvest.planned_supplies.supplies
    assert "Não há fornecimentos previstos" in harvest.answer


async def test_ambiguous_facepe_quantity_remains_a_cited_pending_item(db_session):
    service, _, _ = await _prepare(db_session)
    response = await service.answer_producer_summary(
        "P009",
        session_id=uuid4(),
        reference_date=date(2026, 9, 30),
        period="2026-09-15",
    )
    ambiguous = next(
        row
        for row in response.planned_supplies.supplies
        if row.record_id == "LOT-2026-0099"
    )
    assert ambiguous.observation == "40 maços (kg)"
    assert ambiguous.unit is None
    assert all(total.product != "couve" for total in response.planned_supplies.totals)
    assert any(
        gap.source_ids == [ambiguous.document_source_id]
        for gap in response.gaps_and_divergences
    )
    assert "40 maços (kg)" in response.answer


async def test_operational_delivery_date_units_and_cancel_keep_history(db_session):
    service, _, _ = await _prepare(db_session)
    producer_id = await db_session.scalar(
        select(Producer.id).where(Producer.code == "P004")
    )
    product_id = await db_session.scalar(
        select(Product.id).where(Product.name == "alface")
    )
    orders = order_service(db_session)
    order = await orders.create_order(
        OrderCreate.model_validate(
            {
                "buyer": "Mercado",
                "delivery_start_date": "2026-11-04",
                "delivery_end_date": "2026-11-08",
                "items": [
                    {"product_id": str(product_id), "quantity": "100", "unit": "kg"}
                ],
            }
        )
    )
    item_id = order.items[0].id
    order_id = order.id
    db_session.add_all(
        [
            Lot(
                item_id=item_id,
                producer_id=producer_id,
                quantity=quantity,
                unit=unit,
                delivery_date=date(2026, 11, 6),
                availability_confirmed=True,
            )
            for quantity, unit in [
                (Decimal(2), "kg"),
                (Decimal(500), "g"),
                (Decimal(9), "unidades"),
            ]
        ]
    )
    await db_session.commit()
    session_id = uuid4()
    reference = date(2026, 11, 30)

    async def answer(period):
        return await service.answer_producer_summary(
            "P004",
            session_id=session_id,
            reference_date=reference,
            period=period,
        )

    planned = await answer("2026-11-06")
    assert {(row.unit, row.quantity) for row in planned.planned_supplies.totals} == {
        ("kg", Decimal("2.5")),
        ("un", Decimal(9)),
    }
    assert all(
        row.order_id == order_id
        and row.item_id == item_id
        and row.producer_id == producer_id
        for row in planned.planned_supplies.supplies
    )
    assert str(order_id) in planned.answer
    assert not (await answer("2026-11-05")).planned_supplies.supplies
    assert not planned.financial.sales_in_period.has_records
    assert "não foram encontrados registros de vendas" in planned.answer
    await orders.cancel_order(order_id)
    assert not (await answer("2026-11-06")).planned_supplies.supplies
    assert len((await answer("2026-09-08")).planned_supplies.supplies) == 2


async def test_missing_retrieved_rows_are_reported_without_inventing_lot_references(
    db_session,
):
    await _prepare(db_session)
    service = ProducerSummaryService(
        LotRepository(db_session), InMemoryDocumentSourceProvider()
    )
    response = await service.answer_producer_summary(
        "P004",
        session_id=uuid4(),
        reference_date=date(2026, 9, 30),
        period="2026-09",
    )
    assert response.financial is None
    assert not response.source_ids
    assert not response.planned_supplies.totals
    assert len(response.planned_supplies.pending) == 2
    assert "não foi possível vincular" in response.answer


async def test_aggregate_observation_is_preserved_without_adding_to_totals(db_session):
    service, provider, _ = await _prepare(db_session)
    records = await provider.retrieve_sources(
        DocumentRetrievalContext(session_id=uuid4(), query_text="Lotes da Facepe")
    )
    for record in records.sources:
        if record.record_id == "LOT-2026-0095":
            record.record_fields["observacao"] = "150 maços no total para dois produtos"
    service.source_provider = InMemoryDocumentSourceProvider(
        sources=records.sources,
        financial_records=[],
    )
    response = await service.answer_producer_summary(
        "P004",
        session_id=uuid4(),
        reference_date=date(2026, 9, 30),
        period="2026-09-08",
    )
    assert [
        (row.product, row.quantity) for row in response.planned_supplies.totals
    ] == [
        ("alface", Decimal(300)),
    ]
    assert "150 maços no total para dois produtos" in response.answer
    assert "não foram encontrados registros financeiros" in response.answer
