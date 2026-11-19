from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .lot import Lot


class LotImport(Base):
    __tablename__ = "lot_imports"
    __table_args__ = (
        UniqueConstraint(
            "source_file",
            "record_id",
            name="uq_lot_imports_source_record",
        ),
    )

    lot_id: Mapped[UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="CASCADE"),
        primary_key=True,
    )

    source_file: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    record_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    record_fields: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
    )

    lot: Mapped["Lot"] = relationship()
