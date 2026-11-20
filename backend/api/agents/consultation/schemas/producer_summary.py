from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .financial import FinancialSummaryCalculation
from .response import ConsultationGapOrDivergence, ConsultationResponse


class PlannedSupply(BaseModel):
    lot_id: UUID
    producer_id: UUID
    product: str | None
    delivery_date: date
    quantity: Decimal
    unit: str | None
    origin: Literal["historico", "operacional"]
    order_id: UUID | None = None
    item_id: UUID | None = None
    document_source_id: str | None = None
    record_id: str | None = None
    observation: str | None = None


class PlannedSupplyTotal(BaseModel):
    product: str
    quantity: Decimal
    unit: str


class PlannedSupplySummary(BaseModel):
    supplies: list[PlannedSupply] = Field(default_factory=list)
    totals: list[PlannedSupplyTotal] = Field(default_factory=list)
    pending: list[ConsultationGapOrDivergence] = Field(default_factory=list)


class ProducerSummaryResponse(ConsultationResponse):
    producer_code: str
    producer_name: str
    period_start: date
    period_end: date
    financial: FinancialSummaryCalculation | None
    planned_supplies: PlannedSupplySummary
