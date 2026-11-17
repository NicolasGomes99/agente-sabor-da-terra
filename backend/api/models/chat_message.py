from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key = True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone = True), default=lambda: datetime.now(UTC))