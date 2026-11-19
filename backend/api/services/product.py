from uuid import UUID

from ..models.product import Product
from ..repositories.product import ProductRepository


class ProductNotFoundError(LookupError):
    pass


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    async def list_products(self) -> list[Product]:
        return await self.repository.list_all()

    async def get_product(self, product_id: UUID) -> Product:
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError
        return product
