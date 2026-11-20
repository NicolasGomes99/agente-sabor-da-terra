from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.lot import Lot


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

    async def delete(self, lot: Lot) -> None:
        await self.session.delete(lot)
