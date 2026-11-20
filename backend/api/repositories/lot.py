from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.lot import Lot
from ..models.order import Order
from ..models.order_item import OrderItem


class LotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, lot: Lot) -> None:
        self.session.add(lot)

    async def get_by_id(
        self,
        lot_id: UUID,
        *,
        lock: bool = False,
    ) -> Lot | None:
        statement = (
            select(Lot)
            .where(Lot.id == lot_id)
            .options(selectinload(Lot.producer))
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_planned_supplies(
        self, producer_id: UUID, start: date, end: date,
    ) -> list[Lot]:
        statement = (
            select(Lot)
            .outerjoin(Lot.item)
            .outerjoin(OrderItem.order)
            .where(
                Lot.producer_id == producer_id,
                Lot.delivery_date.between(start, end),
                or_(Lot.item_id.is_(None), Order.cancelled.is_(False)),
            )
            .options(selectinload(Lot.item).selectinload(OrderItem.product))
            .order_by(Lot.delivery_date, Lot.id)
        )
        return list(await self.session.scalars(statement))

    async def delete(self, lot: Lot) -> None:
        await self.session.delete(lot)
