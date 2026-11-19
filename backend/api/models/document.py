from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .citation import Citation


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String)
    storage_key: Mapped[str] = mapped_column(String, unique=True)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_id_record_id", "document_id", "record_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Preenchidos só quando a fonte é uma linha de CSV (ex.: lote_id, id_transacao).
    record_id: Mapped[str | None] = mapped_column(String, nullable=True)
    record_fields: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    citations: Mapped[list["Citation"]] = relationship(back_populates="chunk")