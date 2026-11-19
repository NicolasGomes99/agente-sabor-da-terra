from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user, get_producer_service
from ..schemas.producer import ProducerResponse
from ..services.producer import ProducerNotFoundError, ProducerService

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
    prefix="/producers",
    tags=["producers"],
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

ProducerServiceDependency = Annotated[ProducerService, Depends(get_producer_service)]


@router.get("", response_model=list[ProducerResponse])
async def list_producers(
    service: ProducerServiceDependency, product_id: UUID | None = None,
) -> list[ProducerResponse]:
    return await service.list_producers(product_id=product_id)


@router.get(
    "/{producer_id}",
    response_model=ProducerResponse,
    responses={404: {"description": "Producer not found.", "content": ERROR_DETAIL_CONTENT}},
)
async def get_producer(
    producer_id: UUID, service: ProducerServiceDependency,
) -> ProducerResponse:
    try:
        return await service.get_producer(producer_id)
    except ProducerNotFoundError as error:
        raise HTTPException(status_code=404, detail="Producer not found.") from error
