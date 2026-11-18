from uuid import UUID

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProducerProduct(Base):
    __tablename__ = "producer_products"

    producer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("producers.id"), primary_key=True, nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id"), primary_key=True, nullable=False, index=True,
    )
