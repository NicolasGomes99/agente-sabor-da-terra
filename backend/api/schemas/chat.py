from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    chunk_id: UUID
    document_id: UUID
    document_name: str
    chunk_content: str

    @computed_field
    @property
    def view_url(self) -> str:
        return f"/documents/{self.document_id}/content"

    @computed_field
    @property
    def download_url(self) -> str:
        return f"/documents/{self.document_id}/download"

    @model_validator(mode="before")
    @classmethod
    def from_citation_orm(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        chunk = data.chunk
        document = chunk.document
        return {
            "message_id": data.message_id,
            "chunk_id": data.chunk_id,
            "document_id": document.id,
            "document_name": document.original_filename,
            "chunk_content": chunk.content,
        }


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    created_at: datetime
    citations: list[CitationOut] = []


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]