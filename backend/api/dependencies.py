from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.cloud.storage import Client
from sqlalchemy.ext.asyncio import AsyncSession

from . import database
from .config import (
    get_document_storage_backend,
    get_document_storage_bucket,
    get_document_storage_dir,
)
from .database import get_db
from .models.user import User
from .repositories.document import DocumentRepository
from .repositories.user import UserRepository
from .services.auth import AuthService, InvalidAccessTokenError
from .services.document import DocumentService
from .services.user import UserService
from .storage.base import DocumentStorage
from .storage.gcs import GCSDocumentStorage
from .storage.local import LocalDocumentStorage

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
_gcs_client_lock = Lock()
_gcs_client: Client | None = None


def _get_gcs_client() -> Client:
    global _gcs_client
    with _gcs_client_lock:
        if _gcs_client is None:
            _gcs_client = Client()
        return _gcs_client


def _build_auth_service(session: AsyncSession) -> AuthService:
    user_repository = UserRepository(session)
    user_service = UserService(user_repository)
    return AuthService(user_service)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> AuthService:
    return _build_auth_service(session)


def get_document_storage() -> DocumentStorage:
    if get_document_storage_backend() == "local":
        return LocalDocumentStorage(get_document_storage_dir())

    bucket_name = get_document_storage_bucket()
    return GCSDocumentStorage(_get_gcs_client().bucket(bucket_name))


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> DocumentService:
    return DocumentService(DocumentRepository(session), storage)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    session_maker = database.get_session_maker()
    try:
        async with session_maker() as session:
            user = await _build_auth_service(session).get_current_user(token)
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
