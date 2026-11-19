from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4
from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .citation import Citation


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "position", name="uq_chat_messages_session_position"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(16), default="user", nullable=False
    )

    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
    position: Mapped[int] = mapped_column(Integer)