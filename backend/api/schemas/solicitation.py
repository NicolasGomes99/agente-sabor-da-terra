from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..agents.triage.schemas import TriageAnalysis, TriageInput
from ..models.solicitation import (
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from .chat import MessageOut


class SolicitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    input: TriageInput
    analysis: TriageAnalysis


class SolicitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    summary: str
    request_type: SolicitationType
    urgency: SolicitationUrgency
    status: SolicitationStatus


class SolicitationSessionOut(SolicitationOut):
    title: str
    created_at: datetime
    read_only: bool
    messages: list[MessageOut]


class SolicitationTurnOut(BaseModel):
    operation_id: str
    selected_flow: Literal["triage", "consultation"]
    user_message: MessageOut
    assistant_message: MessageOut
    solicitation: SolicitationOut
