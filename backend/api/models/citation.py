from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .chat_message import ChatMessage
    from .document import DocumentChunk


class Citation(Base):
    __tablename__ = "citations"

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="citations")
    chunk: Mapped["DocumentChunk"] = relationship(back_populates="citations")