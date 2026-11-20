from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChatOperationStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatOperation(Base):
    __tablename__ = "chat_operations"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "operation_key",
            name="uq_chat_operations_session_key",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_chat_operations_status",
        ),
        CheckConstraint(
            "attempt >= 1",
            name="ck_chat_operations_attempt_positive",
        ),
        CheckConstraint(
            "session_generation >= 1",
            name="ck_chat_operations_generation_positive",
        ),
        CheckConstraint(
            "selected_flow IS NULL OR selected_flow IN ('triage', 'consultation')",
            name="ck_chat_operations_selected_flow",
        ),
        Index(
            "ix_chat_operations_session_generation",
            "session_id",
            "session_generation",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    operation_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default=ChatOperationStatus.PROCESSING.value,
        nullable=False,
    )

    attempt: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    session_generation: Mapped[int] = mapped_column(
        BigInteger,
        default=1,
        nullable=False,
    )

    user_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    assistant_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    selected_flow: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    error_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
