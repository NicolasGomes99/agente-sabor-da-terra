from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Product

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_product_persists_with_generated_uuid(db_session: AsyncSession) -> None:
    product = Product(name="Alface")
    db_session.add(product)
    await db_session.flush()
    product_id = product.id
    assert isinstance(product_id, UUID)
    db_session.expunge(product)

    persisted = await db_session.get(Product, product_id)

    assert persisted is not None
    assert persisted.name == "Alface"


async def test_product_persists_with_explicit_uuid(db_session: AsyncSession) -> None:
    product_id = uuid4()
    product = Product(id=product_id, name="Coentro")
    db_session.add(product)
    await db_session.flush()
    db_session.expunge(product)

    persisted = await db_session.get(Product, product_id)

    assert persisted is not None
    assert persisted.id == product_id
    assert persisted.name == "Coentro"


async def test_product_without_name_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(Product(name=None))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("name", ["", "   ", "\t", "\n", " \t\r\n "])
async def test_blank_product_name_is_rejected(db_session: AsyncSession, name: str) -> None:
    db_session.add(Product(name=name))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_duplicate_product_name_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(Product(name="Alface"))
    await db_session.flush()
    db_session.add(Product(name="Alface"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_distinct_product_names_are_allowed(db_session: AsyncSession) -> None:
    first = Product(name="Alface")
    second = Product(name="Coentro")
    db_session.add_all([first, second])
    await db_session.flush()
    first_id, second_id = first.id, second.id
    assert first_id != second_id
    db_session.expunge_all()

    persisted_first = await db_session.get(Product, first_id)
    persisted_second = await db_session.get(Product, second_id)

    assert persisted_first is not None
    assert persisted_second is not None
    assert persisted_first.name == "Alface"
    assert persisted_second.name == "Coentro"
