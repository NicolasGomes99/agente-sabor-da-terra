from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .order_item import OrderItem

class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_orders_version_positive"),
        CheckConstraint(
            "delivery_end_date IS NULL "
            "OR delivery_end_date >= delivery_start_date",
            name="ck_orders_delivery_dates",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )

    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    buyer: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    products: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    conditions: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="",
    )

    delivery_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    delivery_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    cancelled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )
