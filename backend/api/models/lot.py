from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .order_item import OrderItem
    from .producer import Producer


class Lot(Base):
    __tablename__ = "lots"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_lots_quantity_positive"),
        CheckConstraint(
            "unit IS NULL OR unit ~ '[^[:space:]]'",
            name="ck_lots_unit_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    producer_id: Mapped[UUID] = mapped_column(
        ForeignKey("producers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )

    unit: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    delivery_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    availability_confirmed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    item: Mapped["OrderItem | None"] = relationship(
        back_populates="lots",
    )

    producer: Mapped["Producer"] = relationship()
