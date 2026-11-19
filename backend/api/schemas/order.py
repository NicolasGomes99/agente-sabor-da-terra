from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    buyer: str = Field(min_length=1)
    products: str = Field(min_length=1)
    conditions: str = ""

    delivery_start_date: date
    delivery_end_date: date | None = None

    @model_validator(mode="after")
    def validate_delivery_dates(self) -> Self:
        if (
            self.delivery_end_date is not None
            and self.delivery_end_date < self.delivery_start_date
        ):
            raise ValueError(
                "A data final deve ser igual ou posterior à data inicial"
            )
        return self

class OrderResponse(OrderInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID | None
    cancelled: bool
    