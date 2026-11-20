from datetime import date
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from .product import ProductResponse

Quantity = Annotated[
    Decimal,
    Field(
        gt=0,
        max_digits=18,
        decimal_places=3,
        allow_inf_nan=False,
    ),
]


class OrderItemCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    product_id: UUID
    quantity: Quantity
    unit: str = Field(min_length=1)


class OrderItemUpdate(OrderItemCreate):
    id: UUID | None = None


class LotProducerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class LotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID | None
    producer: LotProducerResponse
    quantity: Decimal
    unit: str | None
    delivery_date: date
    availability_confirmed: bool | None


class OrderItemResponse(OrderItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product: ProductResponse
    lots: list[LotResponse] = Field(default_factory=list)
    balance: Decimal | None = None


class OrderBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    buyer: str = Field(min_length=1)
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
                "A data final deve ser igual ou posterior à data inicial."
            )

        return self


class OrderCreate(OrderBase):
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderUpdate(OrderBase):
    version: int = Field(ge=1, strict=True)
    items: list[OrderItemUpdate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_item_ids(self) -> Self:
        item_ids = [
            item.id
            for item in self.items
            if item.id is not None
        ]

        if len(item_ids) != len(set(item_ids)):
            raise ValueError(
                "O mesmo ID de item não pode aparecer mais de uma vez."
            )

        return self


class OrderResponse(OrderBase):
    model_config = ConfigDict(
    from_attributes=True,
    str_strip_whitespace=False,
)

    id: UUID
    version: int = Field(ge=1)
    session_id: UUID | None
    cancelled: bool

    products: str
    items: list[OrderItemResponse]

    @computed_field
    @property
    def needs_item_structuring(self) -> bool:
        return len(self.items) == 0


# Compatibilidade temporária com os imports existentes.
# Removeremos este nome ao atualizar o service e o router.
OrderInput = OrderCreate