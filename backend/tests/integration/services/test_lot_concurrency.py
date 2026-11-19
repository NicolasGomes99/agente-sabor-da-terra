import asyncio
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from api.models import Lot, Order, OrderItem, Producer, ProducerProduct, Product
from api.repositories.lot import LotRepository
from api.repositories.order import OrderRepository
from api.repositories.producer import ProducerRepository
from api.repositories.product import ProductRepository
from api.schemas.lot import LotCreate, LotUpdate
from api.services.lot import (
    LotConflictError,
    LotNotFoundError,
    LotService,
)
from api.services.order import OrderService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def _lot_service(session: AsyncSession) -> LotService:
    return LotService(
        LotRepository(session),
        OrderRepository(session),
        ProducerRepository(session),
    )


def _order_service(session: AsyncSession) -> OrderService:
    return OrderService(OrderRepository(session), ProductRepository(session))


async def _seed(session: AsyncSession) -> SimpleNamespace:
    product = Product(name=f"Tomate {uuid4().hex[:8]}")
    producer = Producer(
        code=f"P{uuid4().hex[:8]}",
        name="Ana Silva",
        cpf=uuid4().hex[:11],
        active=True,
    )
    session.add_all([product, producer])
    await session.flush()
    session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))

    order = Order(
        buyer="Mercado",
        products="",
        conditions="",
        delivery_start_date=date(2026, 11, 4),
        delivery_end_date=date(2026, 11, 8),
    )
    session.add(order)
    await session.flush()
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=Decimal(100),
        unit="kg",
    )
    session.add(item)
    await session.commit()

    return SimpleNamespace(
        order_id=order.id,
        item_id=item.id,
        producer_id=producer.id,
        product_id=product.id,
    )


@pytest_asyncio.fixture
async def env(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SimpleNamespace]:
    async with session_factory() as session:
        data = await _seed(session)

    yield data

    async with session_factory() as session:
        await session.execute(delete(Lot).where(Lot.item_id == data.item_id))
        await session.execute(
            delete(OrderItem).where(OrderItem.id == data.item_id)
        )
        await session.execute(delete(Order).where(Order.id == data.order_id))
        await session.execute(
            delete(ProducerProduct).where(
                ProducerProduct.producer_id == data.producer_id,
                ProducerProduct.product_id == data.product_id,
            )
        )
        await session.execute(
            delete(Producer).where(Producer.id == data.producer_id)
        )
        await session.execute(
            delete(Product).where(Product.id == data.product_id)
        )
        await session.commit()


def _create_payload(producer_id, quantity: str) -> LotCreate:
    return LotCreate.model_validate(
        {
            "producer_id": str(producer_id),
            "quantity": quantity,
            "unit": "kg",
            "delivery_date": "2026-11-04",
            "availability_confirmed": True,
        }
    )


def _update_payload(producer_id, quantity: str) -> LotUpdate:
    return LotUpdate.model_validate(
        {
            "producer_id": str(producer_id),
            "quantity": quantity,
            "unit": "kg",
            "delivery_date": "2026-11-04",
            "availability_confirmed": True,
        }
    )


async def test_concurrent_creates_do_not_exceed_quantity(
    session_factory: async_sessionmaker[AsyncSession],
    env: SimpleNamespace,
) -> None:
    async def create(quantity: str) -> Lot:
        async with session_factory() as session:
            return await _lot_service(session).create(
                env.order_id,
                env.item_id,
                _create_payload(env.producer_id, quantity),
            )

    results = await asyncio.gather(
        create("60"),
        create("60"),
        return_exceptions=True,
    )

    assert sorted(type(result).__name__ for result in results) == [
        "Lot",
        "LotValidationError",
    ]

    async with session_factory() as session:
        lots = list(
            await session.scalars(select(Lot).where(Lot.item_id == env.item_id))
        )
        assert len(lots) == 1
        assert lots[0].quantity == Decimal(60)


async def test_concurrent_create_and_cancel_leaves_no_operational_lots(
    session_factory: async_sessionmaker[AsyncSession],
    env: SimpleNamespace,
) -> None:
    async def create() -> Lot:
        async with session_factory() as session:
            return await _lot_service(session).create(
                env.order_id,
                env.item_id,
                _create_payload(env.producer_id, "40"),
            )

    async def cancel() -> Order:
        async with session_factory() as session:
            return await _order_service(session).cancel_order(env.order_id)

    await asyncio.gather(create(), cancel(), return_exceptions=True)

    async with session_factory() as session:
        order = await session.get(Order, env.order_id)
        assert order.cancelled is True
        lots = list(
            await session.scalars(select(Lot).where(Lot.item_id == env.item_id))
        )
        assert lots == []


async def test_concurrent_edit_and_cancel_leaves_no_operational_lots(
    session_factory: async_sessionmaker[AsyncSession],
    env: SimpleNamespace,
) -> None:
    async with session_factory() as session:
        lot = await _lot_service(session).create(
            env.order_id,
            env.item_id,
            _create_payload(env.producer_id, "40"),
        )
        lot_id = lot.id

    async def edit() -> Lot:
        async with session_factory() as session:
            return await _lot_service(session).update(
                lot_id,
                _update_payload(env.producer_id, "50"),
            )

    async def cancel() -> Order:
        async with session_factory() as session:
            return await _order_service(session).cancel_order(env.order_id)

    await asyncio.gather(edit(), cancel(), return_exceptions=True)

    async with session_factory() as session:
        order = await session.get(Order, env.order_id)
        assert order.cancelled is True
        lots = list(
            await session.scalars(select(Lot).where(Lot.item_id == env.item_id))
        )
        assert lots == []


async def test_concurrent_edit_and_delete_same_lot(
    session_factory: async_sessionmaker[AsyncSession],
    env: SimpleNamespace,
) -> None:
    async with session_factory() as session:
        lot = await _lot_service(session).create(
            env.order_id,
            env.item_id,
            _create_payload(env.producer_id, "40"),
        )
        lot_id = lot.id

    async def edit() -> Lot:
        async with session_factory() as session:
            return await _lot_service(session).update(
                lot_id,
                _update_payload(env.producer_id, "50"),
            )

    async def delete() -> None:
        async with session_factory() as session:
            return await _lot_service(session).delete(lot_id)

    results = await asyncio.gather(edit(), delete(), return_exceptions=True)

    assert all(
        result is None
        or isinstance(result, (Lot, LotNotFoundError, LotConflictError))
        for result in results
    )

    async with session_factory() as session:
        assert await session.get(Lot, lot_id) is None
        item = await session.get(OrderItem, env.item_id)
        assert item is not None
        order = await session.get(Order, env.order_id)
        assert order.cancelled is False
