from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..helpers.units import sum_quantities_in_unit
from .base import Base

if TYPE_CHECKING:
    from .lot import Lot
    from .order import Order
    from .product import Product


class OrderItem(Base):
    __tablename__ = "order_items"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0 AND quantity <> 'NaN'::numeric",
            name="ck_order_items_quantity_positive",
        ),
        CheckConstraint(
            "unit ~ '[^[:space:]]'",
            name="ck_order_items_unit_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    order: Mapped["Order"] = relationship(
        back_populates="items",
    )

    product: Mapped["Product"] = relationship()

    lots: Mapped[list["Lot"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Lot.id",
    )

    @property
    def balance(self) -> Decimal | None:
        allocated = sum_quantities_in_unit(
            [(lot.quantity, lot.unit) for lot in self.lots],
            self.unit,
        )
        if allocated is None:
            return None
        return self.quantity - allocated