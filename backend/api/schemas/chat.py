from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.chat_message import ChatMessageRole


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    position: int
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def serialize_role(cls, role: str) -> str:
        return {ChatMessageRole.USER: "user", ChatMessageRole.AGENT: "assistant"}.get(
            role, role
        )

class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime

class SessionDetail(SessionOut):
    messages: list[MessageOut]
