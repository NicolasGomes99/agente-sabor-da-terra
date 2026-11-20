from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from ..models.chat_message import ChatMessage, ChatMessageRole
from ..models.chat_operation import ChatOperation, ChatOperationStatus


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    operation_id: str | None = Field(default=None, min_length=1, max_length=128)
    retry: bool = False

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message content must not be blank.")
        return stripped

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("operation_id must not be blank.")
        return stripped


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    chunk_id: UUID
    document_id: UUID
    document_name: str
    chunk_content: str
    record_id: str | None = None
    record_fields: dict[str, str] | None = None

    @computed_field
    @property
    def source_type(self) -> str:
        return "record" if self.record_id else "excerpt"

    @computed_field
    @property
    def label(self) -> str:
        if self.record_id:
            return f"{self.document_name} - {self.record_id}"
        return self.document_name

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
            "record_id": chunk.record_id,
            "record_fields": chunk.record_fields,
        }


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    role: str
    content: str
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)

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


class RecoverableOperationOut(BaseModel):
    operation_id: str
    status: Literal["processing", "failed"]
    user_message_id: UUID
    content: str
    attempt: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_operation(
        cls,
        operation: ChatOperation,
        user_message: ChatMessage,
    ) -> "RecoverableOperationOut":
        status_value: Literal["processing", "failed"] = (
            "processing"
            if operation.status == ChatOperationStatus.PROCESSING.value
            else "failed"
        )
        return cls(
            operation_id=operation.operation_key,
            status=status_value,
            user_message_id=user_message.id,
            content=user_message.content,
            attempt=operation.attempt,
            created_at=operation.created_at,
            updated_at=operation.updated_at,
        )


class SessionDetail(SessionOut):
    messages: list[MessageOut]
    pending_operation: RecoverableOperationOut | None = None


class ChatTurnOut(BaseModel):
    operation_id: str
    selected_flow: Literal["triage", "consultation"]
    user_message: MessageOut
    assistant_message: MessageOut