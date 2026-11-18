from uuid import UUID

from ..models.order import Order
from ..models.order_item import OrderItem
from ..models.product import Product
from ..repositories.order import OrderRepository
from ..repositories.product import ProductRepository
from ..schemas.order import (
    OrderCreate,
    OrderItemCreate,
    OrderItemUpdate,
    OrderUpdate,
)


class OrderNotFoundError(LookupError):
    pass


class OrderCancelledError(ValueError):
    pass


class OrderValidationError(ValueError):
    pass


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        product_repository: ProductRepository,
    ) -> None:
        self.repository = repository
        self.product_repository = product_repository

    async def list_orders(self) -> list[Order]:
        return await self.repository.list_all()

    async def get_order(
        self,
        order_id: UUID,
        *,
        lock: bool = False,
    ) -> Order:
        order = await self.repository.get_by_id(
            order_id,
            lock=lock,
        )

        if order is None:
            raise OrderNotFoundError("Pedido não encontrado.")

        return order

    async def _get_products(
        self,
        items: list[OrderItemCreate] | list[OrderItemUpdate],
    ) -> dict[UUID, Product]:
        products: dict[UUID, Product] = {}

        for item in items:
            if item.product_id in products:
                continue

            product = await self.product_repository.get_by_id(
                item.product_id
            )

            if product is None:
                raise OrderValidationError(
                    f"Produto não encontrado: {item.product_id}."
                )

            products[item.product_id] = product

        return products

    def _create_item(
        self,
        data: OrderItemCreate,
        product: Product,
    ) -> OrderItem:
        return OrderItem(
            product_id=product.id,
            product=product,
            quantity=data.quantity,
            unit=data.unit,
        )

    async def create_order(self, data: OrderCreate) -> Order:
        try:
            products = await self._get_products(data.items)

            order = Order(
                buyer=data.buyer,
                products="",
                conditions=data.conditions,
                delivery_start_date=data.delivery_start_date,
                delivery_end_date=data.delivery_end_date,
                items=[
                    self._create_item(
                        item,
                        products[item.product_id],
                    )
                    for item in data.items
                ],
            )

            self.repository.add(order)

            await self.repository.session.commit()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise

    async def update_order(
        self,
        order_id: UUID,
        data: OrderUpdate,
    ) -> Order:
        try:
            order = await self.get_order(
                order_id,
                lock=True,
            )

            if order.cancelled:
                raise OrderCancelledError(
                    "Um pedido cancelado não pode ser editado."
                )

            existing_items = {
                item.id: item
                for item in order.items
            }

            for item_data in data.items:
                if (
                    item_data.id is not None
                    and item_data.id not in existing_items
                ):
                    raise OrderValidationError(
                        "Um dos itens informados não pertence a este pedido."
                    )

            products = await self._get_products(data.items)

            updated_items: list[OrderItem] = []

            for item_data in data.items:
                product = products[item_data.product_id]

                if item_data.id is None:
                    item = self._create_item(
                        item_data,
                        product,
                    )
                else:
                    item = existing_items[item_data.id]

                    item.product_id = product.id
                    item.product = product
                    item.quantity = item_data.quantity
                    item.unit = item_data.unit

                updated_items.append(item)

            order.buyer = data.buyer
            order.conditions = data.conditions
            order.delivery_start_date = data.delivery_start_date
            order.delivery_end_date = data.delivery_end_date

            order.items = updated_items

            await self.repository.session.commit()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise

    async def cancel_order(self, order_id: UUID) -> Order:
        try:
            order = await self.get_order(
                order_id,
                lock=True,
            )

            order.cancelled = True

            await self.repository.session.commit()

            return order

        except Exception:
            await self.repository.session.rollback()
            raise