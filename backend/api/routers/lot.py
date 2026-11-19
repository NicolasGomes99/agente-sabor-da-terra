from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..dependencies import get_current_user, get_lot_service
from ..schemas.lot import LotCreate, LotUpdate
from ..schemas.order import LotResponse
from ..services.lot import (
    LotConflictError,
    LotNotFoundError,
    LotService,
    LotValidationError,
)

router = APIRouter(
    prefix="",
    tags=["lots"],
    dependencies=[Depends(get_current_user)],
)

Service = Annotated[LotService, Depends(get_lot_service)]


@router.post(
    "/orders/{order_id}/items/{item_id}/lots",
    response_model=LotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lot(
    order_id: UUID,
    item_id: UUID,
    payload: LotCreate,
    service: Service,
) -> LotResponse:
    try:
        lot = await service.create(order_id, item_id, payload)
    except LotNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except LotValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except LotConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return LotResponse.model_validate(lot)


@router.put(
    "/lots/{lot_id}",
    response_model=LotResponse,
)
async def update_lot(
    lot_id: UUID,
    payload: LotUpdate,
    service: Service,
) -> LotResponse:
    try:
        lot = await service.update(lot_id, payload)
    except LotNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except LotValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except LotConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return LotResponse.model_validate(lot)


@router.delete(
    "/lots/{lot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_lot(
    lot_id: UUID,
    service: Service,
) -> Response:
    try:
        await service.delete(lot_id)
    except LotNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except LotValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except LotConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
