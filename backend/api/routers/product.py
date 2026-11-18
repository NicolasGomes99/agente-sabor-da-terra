from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user, get_product_service
from ..models.product import Product
from ..schemas.product import ProductResponse
from ..services.product import ProductNotFoundError, ProductService

ERROR_DETAIL_CONTENT = {
    "application/json": {
        "schema": {
            "type": "object",
            "required": ["detail"],
            "properties": {"detail": {"type": "string"}},
        }
    }
}

router = APIRouter(
    prefix="/products",
    tags=["products"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {
            "description": "A valid bearer token is required.",
            "content": ERROR_DETAIL_CONTENT,
            "headers": {
                "WWW-Authenticate": {"schema": {"type": "string", "example": "Bearer"}}
            },
        }
    },
)

ProductServiceDependency = Annotated[ProductService, Depends(get_product_service)]


@router.get("", response_model=list[ProductResponse])
async def list_products(service: ProductServiceDependency) -> list[Product]:
    return await service.list_products()


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"description": "Product not found.", "content": ERROR_DETAIL_CONTENT}},
)
async def get_product(product_id: UUID, service: ProductServiceDependency) -> Product:
    try:
        return await service.get_product(product_id)
    except ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail="Product not found.") from error
