from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from api.models import Product
from api.repositories.product import ProductRepository
from api.services.product import ProductNotFoundError, ProductService

pytestmark = pytest.mark.asyncio


async def test_list_products_returns_repository_products() -> None:
    repository = AsyncMock(spec=ProductRepository)
    products = [
        Product(id=uuid4(), name="Alface"),
        Product(id=uuid4(), name="Coentro"),
    ]
    repository.list_all.return_value = products

    result = await ProductService(repository).list_products()

    assert result == products
    repository.list_all.assert_awaited_once_with()


async def test_list_products_returns_empty_list() -> None:
    repository = AsyncMock(spec=ProductRepository)
    repository.list_all.return_value = []

    result = await ProductService(repository).list_products()

    assert result == []
    repository.list_all.assert_awaited_once_with()


async def test_get_product_returns_existing_product() -> None:
    repository = AsyncMock(spec=ProductRepository)
    product_id = uuid4()
    product = Product(id=product_id, name="Alface")
    repository.get_by_id.return_value = product

    result = await ProductService(repository).get_product(product_id)

    assert result is product
    repository.get_by_id.assert_awaited_once_with(product_id)


async def test_get_product_raises_for_unknown_id() -> None:
    repository = AsyncMock(spec=ProductRepository)
    product_id = uuid4()
    repository.get_by_id.return_value = None

    with pytest.raises(ProductNotFoundError):
        await ProductService(repository).get_product(product_id)

    repository.get_by_id.assert_awaited_once_with(product_id)
