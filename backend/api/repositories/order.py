from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order import Order


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def add(self, order: Order) -> None:
        self.session.add(order)

    async def list_all(self) -> list[Order]:
        statement = select(Order).order_by(Order.id)
        result = await self.session.scalars(statement)

        return list(result)

    async def get_by_id(
            self,
            order_id: UUID,
            *,
            lock: bool = False,
    ) -> Order | None:
        statement = select(Order).where(Order.id == order_id)

        if lock:
            statement = statement.with_for_update()

        return await self.session.scalar(statement)


