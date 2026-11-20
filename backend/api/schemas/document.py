from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str


class DocumentIndexingStatusResponse(BaseModel):
    id: UUID
    original_filename: str
    processing_status: Literal["pending", "processing", "indexed", "failed"]
    processing_error: str | None = None
    indexed_at: datetime | None = None
    chunk_count: int = 0
