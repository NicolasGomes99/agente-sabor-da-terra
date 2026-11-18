from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Product
from api.repositories.product import ProductRepository

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_list_all_returns_products_ordered_by_name(db_session: AsyncSession) -> None:
    coentro_id, alface_id, banana_id = uuid4(), uuid4(), uuid4()
    db_session.add_all([
        Product(id=coentro_id, name="Coentro"),
        Product(id=alface_id, name="Alface"),
        Product(id=banana_id, name="Banana"),
    ])
    await db_session.flush()
    db_session.expunge_all()

    products = await ProductRepository(db_session).list_all()

    assert [(product.id, product.name) for product in products] == [
        (alface_id, "Alface"),
        (banana_id, "Banana"),
        (coentro_id, "Coentro"),
    ]


async def test_list_all_returns_empty_list(db_session: AsyncSession) -> None:
    assert await ProductRepository(db_session).list_all() == []


async def test_get_by_id_returns_existing_product(db_session: AsyncSession) -> None:
    product_id = uuid4()
    db_session.add(Product(id=product_id, name="Alface"))
    await db_session.flush()
    db_session.expunge_all()

    product = await ProductRepository(db_session).get_by_id(product_id)

    assert product is not None
    assert product.id == product_id
    assert product.name == "Alface"


async def test_get_by_id_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    db_session.add(Product(name="Alface"))
    await db_session.flush()

    assert await ProductRepository(db_session).get_by_id(uuid4()) is None
