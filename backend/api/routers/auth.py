from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_auth_service
from ..schemas.auth import LoginRequest, LoginResponse
from ..services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    user = await auth_service.authenticate_user(
        credentials.email,
        credentials.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LoginResponse(
        access_token=auth_service.create_access_token(user.id),
    )