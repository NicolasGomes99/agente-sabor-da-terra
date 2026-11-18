from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .product import ProductResponse


class ProducerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    cpf: str
    active: bool
    phone: str | None
    email: str | None
    address: str | None
    municipality: str | None
    products: list[ProductResponse]
