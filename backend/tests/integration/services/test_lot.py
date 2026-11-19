from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Lot, Order, OrderItem, Producer, ProducerProduct, Product
from api.repositories.lot import LotRepository
from api.repositories.order import OrderRepository
from api.repositories.producer import ProducerRepository
from api.schemas.lot import LotCreate, LotUpdate
from api.schemas.order import OrderResponse
from api.services.lot import (
    LotConflictError,
    LotNotFoundError,
    LotService,
    LotValidationError,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service(db_session: AsyncSession) -> LotService:
    return LotService(
        LotRepository(db_session),
        OrderRepository(db_session),
        ProducerRepository(db_session),
    )


@pytest_asyncio.fixture
async def environment(db_session: AsyncSession) -> SimpleNamespace:
    product = Product(name="Tomate")
    active = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    inactive = Producer(code="P002", name="João Silva", cpf="12345678901", active=False)
    db_session.add_all([product, active, inactive])
    await db_session.flush()

    db_session.add_all([
        ProducerProduct(producer_id=active.id, product_id=product.id),
        ProducerProduct(producer_id=inactive.id, product_id=product.id),
    ])

    order = Order(
        buyer="Mercado Central",
        products="",
        conditions="",
        delivery_start_date=date(2026, 11, 4),
        delivery_end_date=date(2026, 11, 8),
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
    await db_session.commit()

    return SimpleNamespace(
        product=product,
        active=active,
        inactive=inactive,
        order=order,
        item=item,
    )


def create_payload(producer_id: UUID, **overrides) -> LotCreate:
    data = {
        "producer_id": str(producer_id),
        "quantity": "10",
        "unit": "kg",
        "delivery_date": "2026-11-04",
        "availability_confirmed": True,
        **overrides,
    }
    return LotCreate.model_validate(data)


def update_payload(producer_id: UUID, **overrides) -> LotUpdate:
    return LotUpdate.model_validate(create_payload(producer_id, **overrides).model_dump())


async def order_snapshot(db_session: AsyncSession, order_id: UUID) -> dict:
    order = await OrderRepository(db_session).get_by_id(order_id)
    return OrderResponse.model_validate(order).model_dump(mode="json")


async def test_create_lot_persists_and_updates_balance(
    service: LotService,
    db_session: AsyncSession,
    environment: SimpleNamespace,
) -> None:
    lot = await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, quantity="40"),
    )
    assert lot.item_id == environment.item.id
    assert lot.availability_confirmed is True

    snapshot = await order_snapshot(db_session, environment.order.id)
    item = snapshot["items"][0]
    assert len(item["lots"]) == 1
    assert item["lots"][0]["producer"]["name"] == "Ana Silva"
    assert item["balance"] == "60.000"


async def test_create_rejects_inactive_producer(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    with pytest.raises(LotValidationError, match="inativo"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.inactive.id),
        )


async def test_create_rejects_producer_not_linked_to_product(
    service: LotService,
    db_session: AsyncSession,
    environment: SimpleNamespace,
) -> None:
    unrelated = Producer(code="P003", name="Outro", cpf="23456789012", active=True)
    db_session.add(unrelated)
    await db_session.commit()

    with pytest.raises(LotValidationError, match="não fornece"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(unrelated.id),
        )


async def test_create_accepts_interval_extremes_and_rejects_outside(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, delivery_date="2026-11-04"),
    )
    await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, delivery_date="2026-11-08"),
    )

    with pytest.raises(LotValidationError, match="fora do prazo"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.active.id, delivery_date="2026-11-09"),
        )


async def test_create_requires_confirmation(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    with pytest.raises(LotValidationError, match="Confirme"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.active.id, availability_confirmed=False),
        )


async def test_create_rejects_quantity_above_balance(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, quantity="90"),
    )

    with pytest.raises(LotValidationError, match="saldo"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.active.id, quantity="20"),
        )


async def test_create_rejects_incompatible_unit(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    with pytest.raises(LotValidationError, match="equivalência"):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.active.id, unit="caixa"),
        )


async def test_update_replaces_quantity_and_requires_new_confirmation_on_change(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    order_id = environment.order.id
    item_id = environment.item.id
    active_id = environment.active.id

    lot = await service.create(
        order_id,
        item_id,
        create_payload(active_id, quantity="10"),
    )
    lot_id = lot.id

    with pytest.raises(LotValidationError, match="Confirme novamente"):
        await service.update(
            lot_id,
            update_payload(active_id, quantity="20", availability_confirmed=False),
        )

    updated = await service.update(
        lot_id,
        update_payload(active_id, quantity="20", availability_confirmed=True),
    )
    assert updated.quantity == Decimal(20)


async def test_update_rejects_quantity_above_balance_excluding_itself(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    lot = await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, quantity="10"),
    )
    await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id, quantity="80"),
    )

    with pytest.raises(LotValidationError, match="saldo"):
        await service.update(
            lot.id,
            update_payload(environment.active.id, quantity="30", availability_confirmed=True),
        )


async def test_delete_removes_lot(
    service: LotService,
    db_session: AsyncSession,
    environment: SimpleNamespace,
) -> None:
    lot = await service.create(
        environment.order.id,
        environment.item.id,
        create_payload(environment.active.id),
    )
    await service.delete(lot.id)
    assert await db_session.scalar(select(Lot).where(Lot.id == lot.id)) is None


async def test_delete_rejects_imported_lot(
    service: LotService,
    db_session: AsyncSession,
    environment: SimpleNamespace,
) -> None:
    imported = Lot(
        item_id=None,
        producer_id=environment.active.id,
        quantity=Decimal(300),
        unit=None,
        delivery_date=date(2026, 9, 8),
    )
    db_session.add(imported)
    await db_session.commit()

    with pytest.raises(LotValidationError, match="importados"):
        await service.delete(imported.id)


async def test_create_on_cancelled_order_is_rejected(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    environment.order.cancelled = True
    await service.repository.session.commit()

    with pytest.raises(LotConflictError):
        await service.create(
            environment.order.id,
            environment.item.id,
            create_payload(environment.active.id),
        )


async def test_create_with_unknown_item_raises_not_found(
    service: LotService,
    environment: SimpleNamespace,
) -> None:
    with pytest.raises(LotNotFoundError):
        await service.create(
            environment.order.id,
            uuid4(),
            create_payload(environment.active.id),
        )
