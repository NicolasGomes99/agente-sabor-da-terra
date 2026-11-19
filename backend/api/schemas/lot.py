from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .order import Quantity


class LotBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    producer_id: UUID
    quantity: Quantity
    unit: str = Field(min_length=1)
    delivery_date: date
    availability_confirmed: bool


class LotCreate(LotBase):
    pass


class LotUpdate(LotBase):
    pass
