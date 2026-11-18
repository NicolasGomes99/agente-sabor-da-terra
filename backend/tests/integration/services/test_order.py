from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from api.models.order import Order
from api.models.order_item import OrderItem
from api.models.product import Product
from api.repositories.order import OrderRepository
from api.repositories.product import ProductRepository
from api.schemas.order import OrderCreate, OrderResponse, OrderUpdate
from api.services.order import OrderCancelledError, OrderService, OrderValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service(db_session: AsyncSession) -> OrderService:
    return OrderService(
        OrderRepository(db_session),
        ProductRepository(db_session),
    )


@pytest_asyncio.fixture
async def product_ids(db_session: AsyncSession) -> tuple[UUID, UUID]:
    first, second = uuid4(), uuid4()
    db_session.add_all(
        [
            Product(id=first, name=f"Tomate {first}"),
            Product(id=second, name=f"Alface {second}"),
        ]
    )
    await db_session.commit()
    return first, second


def item(product_id: UUID, quantity: str = "10", unit: str = "kg", **extra) -> dict:
    return {"product_id": product_id, "quantity": quantity, "unit": unit, **extra}


def create_payload(items: list[dict]) -> OrderCreate:
    return OrderCreate.model_validate(
        {
            "buyer": "Mercado Central",
            "conditions": "Entrega pela manhã",
            "delivery_start_date": "2026-12-05",
            "items": items,
        }
    )


def update_payload(items: list[dict]) -> OrderUpdate:
    return OrderUpdate.model_validate(
        {
            "buyer": "Comprador atualizado",
            "conditions": "Entrega à tarde",
            "delivery_start_date": "2026-12-06",
            "delivery_end_date": "2026-12-08",
            "items": items,
        }
    )


async def snapshot(service: OrderService, order_id: UUID) -> dict:
    order = await service.get_order(order_id)
    return OrderResponse.model_validate(order).model_dump(mode="json")


async def test_create_persists_two_items_and_loads_their_products(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, second = product_ids
    created = await service.create_order(
        create_payload(
            [
                item(first, "10.125"),
                item(second, "5", "unidades"),
            ]
        )
    )
    saved = await snapshot(service, created.id)
    assert len(saved["items"]) == 2
    assert len({record["id"] for record in saved["items"]}) == 2
    assert {record["product_id"] for record in saved["items"]} == {
        str(first),
        str(second),
    }
    assert all(record["product"]["name"] for record in saved["items"])
    assert saved["needs_item_structuring"] is False


async def test_update_keeps_ids_when_quantity_or_unit_changes(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, second = product_ids
    order = await service.create_order(create_payload([item(first), item(second)]))
    before = await snapshot(service, order.id)
    ids = {record["product_id"]: record["id"] for record in before["items"]}
    order_id = order.id
    await service.update_order(
        order_id,
        update_payload(
            [
                item(first, "20", "kg", id=ids[str(first)]),
                item(second, "5", "unidades", id=ids[str(second)]),
            ]
        ),
    )
    saved = await snapshot(service, order_id)
    assert {record["product_id"]: record["id"] for record in saved["items"]} == ids
    by_product = {record["product_id"]: record for record in saved["items"]}
    assert float(by_product[str(first)]["quantity"]) == 20
    assert by_product[str(second)]["unit"] == "unidades"
    assert saved["delivery_end_date"] == "2026-12-08"


async def test_update_removes_omitted_item_and_creates_new_item(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
    db_session: AsyncSession,
) -> None:
    first, second = product_ids
    order = await service.create_order(create_payload([item(first)]))
    order_id, removed_id = order.id, order.items[0].id
    await service.update_order(
        order_id, update_payload([item(second, "3", "unidades")])
    )
    saved = await snapshot(service, order_id)
    assert len(saved["items"]) == 1
    assert saved["items"][0]["id"] != str(removed_id)
    assert saved["items"][0]["product_id"] == str(second)
    assert await db_session.get(OrderItem, removed_id) is None


async def test_invalid_product_rejects_entire_creation(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
    db_session: AsyncSession,
) -> None:
    first, _ = product_ids
    before_orders = await db_session.scalar(select(func.count()).select_from(Order))
    before_items = await db_session.scalar(select(func.count()).select_from(OrderItem))
    with pytest.raises(OrderValidationError):
        await service.create_order(create_payload([item(first), item(uuid4())]))
    assert (
        await db_session.scalar(select(func.count()).select_from(Order))
        == before_orders
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(OrderItem))
        == before_items
    )


async def test_invalid_product_preserves_entire_existing_order(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, _ = product_ids
    order = await service.create_order(create_payload([item(first)]))
    order_id, item_id = order.id, order.items[0].id
    before = await snapshot(service, order_id)
    with pytest.raises(OrderValidationError):
        await service.update_order(
            order_id,
            update_payload(
                [
                    item(first, "99", id=item_id),
                    item(uuid4()),
                ]
            ),
        )
    assert await snapshot(service, order_id) == before


async def test_item_from_another_order_is_rejected_without_changing_either(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, second = product_ids
    order_a = await service.create_order(create_payload([item(first)]))
    order_b = await service.create_order(create_payload([item(second)]))
    id_a, id_b, foreign_item_id = order_a.id, order_b.id, order_b.items[0].id
    before_a, before_b = await snapshot(service, id_a), await snapshot(service, id_b)
    with pytest.raises(OrderValidationError):
        await service.update_order(
            id_a,
            update_payload(
                [
                    item(second, "999", id=foreign_item_id),
                ]
            ),
        )
    assert await snapshot(service, id_a) == before_a
    assert await snapshot(service, id_b) == before_b


async def test_unknown_item_id_is_rejected(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, _ = product_ids
    order = await service.create_order(create_payload([item(first)]))
    order_id = order.id
    before = await snapshot(service, order_id)
    with pytest.raises(OrderValidationError):
        await service.update_order(order_id, update_payload([item(first, id=uuid4())]))
    assert await snapshot(service, order_id) == before


async def test_legacy_order_can_be_structured_without_losing_original_text(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
    db_session: AsyncSession,
) -> None:
    first, _ = product_ids
    legacy_id = uuid4()
    description = "  Tomate: 10 kg; condições originais preservadas\n"
    db_session.add(
        Order(
            id=legacy_id,
            buyer="Comprador antigo",
            products=description,
            conditions="Manhã",
            delivery_start_date=date(2026, 12, 5),
            delivery_end_date=None,
            cancelled=False,
        )
    )
    await db_session.commit()
    before = await snapshot(service, legacy_id)
    assert before["items"] == []
    assert before["products"] == description
    assert before["needs_item_structuring"] is True
    await service.update_order(legacy_id, update_payload([item(first)]))
    after = await snapshot(service, legacy_id)
    assert after["products"] == description
    assert len(after["items"]) == 1
    assert after["needs_item_structuring"] is False


async def test_cancel_preserves_items_and_rejects_further_edits(
    service: OrderService,
    product_ids: tuple[UUID, UUID],
) -> None:
    first, _ = product_ids
    order = await service.create_order(create_payload([item(first)]))
    order_id, item_id = order.id, order.items[0].id
    before = await snapshot(service, order_id)
    await service.cancel_order(order_id)
    after = await snapshot(service, order_id)
    assert after == {**before, "cancelled": True}
    with pytest.raises(OrderCancelledError):
        await service.update_order(
            order_id, update_payload([item(first, "99", id=item_id)])
        )
    assert await snapshot(service, order_id) == after
