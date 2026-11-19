from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Producer, ProducerProduct, Product

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest_asyncio.fixture
async def references(db_session: AsyncSession) -> tuple[UUID, UUID]:
    producer = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    product = Product(name="Alface")
    db_session.add_all([producer, product])
    await db_session.flush()
    return producer.id, product.id


async def test_producer_product_persists_with_composite_key(
    db_session: AsyncSession, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    db_session.add(ProducerProduct(producer_id=producer_id, product_id=product_id))
    await db_session.flush()
    db_session.expunge_all()

    association = await db_session.get(ProducerProduct, references)

    assert association is not None
    assert association.producer_id == producer_id
    assert association.product_id == product_id


async def test_producer_can_supply_multiple_products(
    db_session: AsyncSession, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    other_product = Product(name="Coentro")
    db_session.add(other_product)
    await db_session.flush()
    expected_ids = {product_id, other_product.id}
    db_session.add_all([
        ProducerProduct(producer_id=producer_id, product_id=value)
        for value in expected_ids
    ])
    await db_session.flush()
    db_session.expunge_all()

    product_ids = await db_session.scalars(
        select(ProducerProduct.product_id).where(ProducerProduct.producer_id == producer_id)
    )

    assert set(product_ids) == expected_ids


async def test_product_can_have_multiple_producers(
    db_session: AsyncSession, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    other_producer = Producer(code="P002", name="João Silva", cpf="12345678901", active=False)
    db_session.add(other_producer)
    await db_session.flush()
    expected_ids = {producer_id, other_producer.id}
    db_session.add_all([
        ProducerProduct(producer_id=value, product_id=product_id)
        for value in expected_ids
    ])
    await db_session.flush()
    db_session.expunge_all()

    producer_ids = await db_session.scalars(
        select(ProducerProduct.producer_id).where(ProducerProduct.product_id == product_id)
    )

    assert set(producer_ids) == expected_ids


async def test_producer_and_product_can_exist_without_associations(
    db_session: AsyncSession, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    db_session.expunge_all()

    assert await db_session.get(Producer, producer_id) is not None
    assert await db_session.get(Product, product_id) is not None
    assert list(await db_session.scalars(select(ProducerProduct))) == []


async def test_duplicate_producer_product_is_rejected(
    db_session: AsyncSession, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    db_session.add(ProducerProduct(producer_id=producer_id, product_id=product_id))
    await db_session.flush()
    db_session.expunge_all()
    db_session.add(ProducerProduct(producer_id=producer_id, product_id=product_id))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("missing_reference", ["producer", "product"])
async def test_producer_product_requires_existing_references(
    db_session: AsyncSession, references: tuple[UUID, UUID], missing_reference: str,
) -> None:
    producer_id, product_id = references
    db_session.add(ProducerProduct(
        producer_id=uuid4() if missing_reference == "producer" else producer_id,
        product_id=uuid4() if missing_reference == "product" else product_id,
    ))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("referenced_model", [Producer, Product])
async def test_referenced_records_cannot_be_deleted(
    db_session: AsyncSession, references: tuple[UUID, UUID],
    referenced_model: type[Producer] | type[Product],
) -> None:
    producer_id, product_id = references
    db_session.add(ProducerProduct(producer_id=producer_id, product_id=product_id))
    await db_session.flush()
    record_id = producer_id if referenced_model is Producer else product_id

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(delete(referenced_model).where(referenced_model.id == record_id))
    db_session.expunge_all()

    assert await db_session.get(Producer, producer_id) is not None
    assert await db_session.get(Product, product_id) is not None
    assert await db_session.get(ProducerProduct, references) is not None
