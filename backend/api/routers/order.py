from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user, get_order_service
from ..models.order import Order
from ..schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
)
from ..services.order import (
    OrderCancelledError,
    OrderConflictError,
    OrderNotFoundError,
    OrderService,
    OrderValidationError,
)

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(get_current_user)],
)

Service = Annotated[OrderService, Depends(get_order_service)]


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    service: Service,
) -> Order:
    try:
        return await service.create_order(payload)

    except OrderValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("", response_model=list[OrderResponse])
async def list_orders(service: Service) -> list[Order]:
    return await service.list_orders()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: UUID, service: Service) -> Order:
    try:
        return await service.get_order(order_id)
    except OrderNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.put(
    "/{order_id}",
    response_model=OrderResponse,
)
async def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    service: Service,
) -> Order:
    try:
        return await service.update_order(
            order_id,
            payload,
        )

    except OrderNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    except OrderConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "order_version_conflict", "message": str(error)},
        ) from error

    except OrderCancelledError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    except OrderValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(order_id: UUID, service: Service) -> Order:
    try:
        return await service.cancel_order(order_id)
    except OrderNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error