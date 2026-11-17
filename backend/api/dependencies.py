from typing import Annotated

from backend.api.repositories.chat import ChatRepository
from backend.api.services.chat import ChatService
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models.user import User
from .repositories.user import UserRepository
from .services.auth import AuthService, InvalidAccessTokenError
from .services.user import UserService


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthService:
    user_repository = UserRepository(session)
    user_service = UserService(user_repository)
    return AuthService(user_service)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    try:
        user = await auth_service.get_current_user(token)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ChatService:
    return ChatService(ChatRepository(session))