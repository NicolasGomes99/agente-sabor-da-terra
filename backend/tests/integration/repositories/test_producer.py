from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Producer, ProducerProduct, Product
from api.repositories.producer import ProducerRepository

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest_asyncio.fixture
async def catalog(db_session: AsyncSession) -> tuple[list[Producer], list[Product]]:
    producers = [
        Producer(
            id=UUID(int=1), code="P001", name="Ana Silva", cpf="01234567890", active=True,
            phone="81999990000", email="ana@example.com", address="Rua das Flores, 10",
            municipality="Caruaru",
        ),
        Producer(id=UUID(int=2), code="P002", name="Ana Silva", cpf="12345678901", active=False),
        Producer(id=UUID(int=3), code="P003", name="Bruno Silva", cpf="23456789012", active=True),
    ]
    products = [Product(name=name) for name in ("Alface", "Banana", "Coentro", "Tomate")]
    db_session.add_all([*reversed(producers), *reversed(products)])
    await db_session.flush()
    db_session.add_all([
        ProducerProduct(producer_id=producers[0].id, product_id=products[2].id),
        ProducerProduct(producer_id=producers[1].id, product_id=products[1].id),
        ProducerProduct(producer_id=producers[1].id, product_id=products[0].id),
        ProducerProduct(producer_id=producers[0].id, product_id=products[0].id),
    ])
    await db_session.flush()
    db_session.expunge_all()
    return producers, products


async def test_list_all_returns_producers_ordered_by_name_and_id(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    producers, _ = catalog

    result = await ProducerRepository(db_session).list_all()

    assert [(producer.id, producer.name, producer.active) for producer in result] == [
        (producer.id, producer.name, producer.active) for producer in producers
    ]


async def test_list_all_returns_empty_list(db_session: AsyncSession) -> None:
    assert await ProducerRepository(db_session).list_all() == []


async def test_list_all_filters_by_product(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    producers, products = catalog

    result = await ProducerRepository(db_session).list_all(product_id=products[0].id)

    assert [(producer.id, producer.active) for producer in result] == [
        (producers[0].id, True), (producers[1].id, False),
    ]


@pytest.mark.parametrize("unknown_product", [False, True])
async def test_list_all_returns_empty_list_for_product_without_suppliers(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
    unknown_product: bool,
) -> None:
    _, products = catalog
    product_id = uuid4() if unknown_product else products[3].id

    assert await ProducerRepository(db_session).list_all(product_id=product_id) == []


@pytest.mark.parametrize("producer_index", [0, 1])
async def test_get_by_id_returns_existing_producer(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
    producer_index: int,
) -> None:
    producers, _ = catalog
    expected = producers[producer_index]

    result = await ProducerRepository(db_session).get_by_id(expected.id)

    assert result is not None
    fields = ("id", "code", "name", "cpf", "active", "phone", "email", "address", "municipality")
    assert {field: getattr(result, field) for field in fields} == {
        field: getattr(expected, field) for field in fields
    }


async def test_get_by_id_returns_none_for_unknown_id(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    assert await ProducerRepository(db_session).get_by_id(uuid4()) is None


async def test_list_products_by_producer_ids_groups_and_orders_products(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    producers, products = catalog

    result = await ProducerRepository(db_session).list_products_by_producer_ids(
        [producers[1].id, producers[0].id]
    )

    assert {
        producer_id: [(product.id, product.name) for product in associated]
        for producer_id, associated in result.items()
    } == {
        producers[0].id: [(products[0].id, "Alface"), (products[2].id, "Coentro")],
        producers[1].id: [(products[0].id, "Alface"), (products[1].id, "Banana")],
    }


async def test_list_products_by_producer_ids_excludes_unrequested_producers(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    producers, products = catalog

    result = await ProducerRepository(db_session).list_products_by_producer_ids([producers[0].id])

    assert set(result) == {producers[0].id}
    assert [product.id for product in result[producers[0].id]] == [products[0].id, products[2].id]


async def test_list_products_by_producer_ids_includes_producers_without_products(
    db_session: AsyncSession, catalog: tuple[list[Producer], list[Product]],
) -> None:
    producers, products = catalog

    result = await ProducerRepository(db_session).list_products_by_producer_ids(
        [producers[0].id, producers[2].id]
    )

    assert set(result) == {producers[0].id, producers[2].id}
    assert [product.id for product in result[producers[0].id]] == [products[0].id, products[2].id]
    assert result[producers[2].id] == []


async def test_list_products_by_producer_ids_skips_database_for_empty_input() -> None:
    session = AsyncMock(spec=AsyncSession)

    assert await ProducerRepository(session).list_products_by_producer_ids([]) == {}
    assert session.mock_calls == []
