from uuid import UUID

from ..models.order import Order
from ..repositories.order import OrderRepository
from ..schemas.order import OrderInput


class OrderNotFoundError(LookupError):
    pass

class OrderCancelledError(ValueError):
    pass

class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    async def list_orders(self) -> list[Order]:
        return await self.repository.list_all()

    async def get_order(
            self,
            order_id: UUID,
            *,
            lock: bool = False,
    ) -> Order:
        order = await self.repository.get_by_id(order_id, lock=lock)

        if order is None:
            raise OrderNotFoundError("Pedido não encontrado.")

        return order

    async def create_order(self, data: OrderInput) -> Order:
        order = Order(**data.model_dump())

        self.repository.add(order)
        await self._commit()

        return order

    async def update_order(
            self,
            order_id: UUID,
            data: OrderInput,
    ) -> Order:
        order = await self.get_order(order_id, lock=True)

        if order.cancelled:
            raise OrderCancelledError(
                "Um pedido cancelado não pode ser editado."
            )

        order.buyer = data.buyer
        order.products = data.products
        order.conditions = data.conditions
        order.delivery_start_date = data.delivery_start_date
        order.delivery_end_date = data.delivery_end_date

        await self._commit()

        return order

    async def cancel_order(self, order_id: UUID) -> Order:
        order = await self.get_order(order_id, lock=True)

        order.cancelled = True
        await self._commit()

        return order

    async def _commit(self) -> None:
        try:
            await self.repository.session.commit()
        except Exception:
            await self.repository.session.rollback()
            raise