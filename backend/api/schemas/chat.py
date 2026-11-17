from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    created_at: datetime

class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime

class SessionDetail(SessionOut):
    messages: list[MessageOut]