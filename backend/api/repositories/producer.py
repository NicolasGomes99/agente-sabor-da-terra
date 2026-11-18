from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.producer import Producer
from ..models.producer_product import ProducerProduct
from ..models.product import Product


class ProducerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, product_id: UUID | None = None) -> list[Producer]:
        statement = select(Producer).order_by(Producer.name, Producer.id)
        if product_id is not None:
            statement = statement.join(
                ProducerProduct, ProducerProduct.producer_id == Producer.id
            ).where(ProducerProduct.product_id == product_id)
        result = await self.session.scalars(statement)
        return list(result)

    async def get_by_id(self, producer_id: UUID) -> Producer | None:
        return await self.session.get(Producer, producer_id)

    async def list_products_by_producer_ids(
        self, producer_ids: list[UUID],
    ) -> dict[UUID, list[Product]]:
        products_by_producer: dict[UUID, list[Product]] = {
            producer_id: [] for producer_id in producer_ids
        }
        if not producer_ids:
            return products_by_producer

        statement = (
            select(ProducerProduct.producer_id, Product)
            .join(Product, ProducerProduct.product_id == Product.id)
            .where(ProducerProduct.producer_id.in_(producer_ids))
            .order_by(Product.name, Product.id)
        )
        result = await self.session.execute(statement)
        for producer_id, product in result:
            products_by_producer[producer_id].append(product)
        return products_by_producer
