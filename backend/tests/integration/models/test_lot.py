from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Lot, Order, OrderItem, Producer, Product

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def _producer(db_session: AsyncSession) -> Producer:
    producer = Producer(
        code="P001",
        name="Ana Silva",
        cpf="01234567890",
        active=True,
    )
    db_session.add(producer)
    await db_session.flush()
    return producer


async def test_lot_persists_without_item_for_historical_load(
    db_session: AsyncSession,
) -> None:
    producer = await _producer(db_session)
    lot = Lot(
        item_id=None,
        producer_id=producer.id,
        quantity=Decimal(300),
        unit=None,
        delivery_date=date(2026, 9, 8),
        availability_confirmed=None,
    )
    db_session.add(lot)
    await db_session.flush()
    lot_id = lot.id

    assert isinstance(lot_id, UUID)
    db_session.expunge_all()

    persisted = await db_session.get(Lot, lot_id)
    assert persisted is not None
    assert persisted.item_id is None
    assert persisted.unit is None
    assert persisted.availability_confirmed is None
    assert persisted.delivery_date == date(2026, 9, 8)
    assert persisted.quantity == Decimal(300)


async def test_lot_requires_existing_producer(db_session: AsyncSession) -> None:
    db_session.add(Lot(
        producer_id=uuid4(),
        quantity=Decimal(10),
        unit="kg",
        delivery_date=date(2026, 12, 5),
    ))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_lot_requires_existing_item_when_linked(db_session: AsyncSession) -> None:
    producer = await _producer(db_session)
    db_session.add(Lot(
        item_id=uuid4(),
        producer_id=producer.id,
        quantity=Decimal(10),
        unit="kg",
        delivery_date=date(2026, 12, 5),
    ))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_lot_rejects_non_positive_quantity(db_session: AsyncSession) -> None:
    producer = await _producer(db_session)
    for quantity in (Decimal(0), Decimal(-1)):
        db_session.add(Lot(
            producer_id=producer.id,
            quantity=quantity,
            unit="kg",
            delivery_date=date(2026, 12, 5),
        ))

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


async def test_lot_rejects_blank_unit_when_present(db_session: AsyncSession) -> None:
    producer = await _producer(db_session)
    db_session.add(Lot(
        producer_id=producer.id,
        quantity=Decimal(10),
        unit="   ",
        delivery_date=date(2026, 12, 5),
    ))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_lot_links_to_order_item(db_session: AsyncSession) -> None:
    producer = await _producer(db_session)
    product = Product(name="Tomate")
    db_session.add(product)
    await db_session.flush()

    order = Order(
        buyer="Mercado",
        products="",
        conditions="",
        delivery_start_date=date(2026, 12, 5),
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=Decimal(100),
        unit="kg",
    )
    db_session.add(item)
    await db_session.flush()

    lot = Lot(
        item_id=item.id,
        producer_id=producer.id,
        quantity=Decimal(10),
        unit="kg",
        delivery_date=date(2026, 12, 5),
        availability_confirmed=True,
    )
    db_session.add(lot)
    await db_session.flush()
    lot_id = lot.id
    db_session.expunge_all()

    persisted = await db_session.get(Lot, lot_id)
    assert persisted is not None
    assert persisted.item_id == item.id
    assert persisted.availability_confirmed is True
