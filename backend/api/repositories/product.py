from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.product import Product


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Product]:
        statement = select(Product).order_by(Product.name, Product.id)
        result = await self.session.scalars(statement)
        return list(result)

    async def get_by_id(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)
