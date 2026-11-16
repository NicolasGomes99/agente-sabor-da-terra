import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from ..models.user import User
from .user import UserService

JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
password_hash = PasswordHash.recommended()


class InvalidAccessTokenError(ValueError):
    pass


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        *,
        secret_key: str | None = None,
        access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    ) -> None:
        self.users = user_service
        resolved_secret_key = secret_key or os.getenv("JWT_SECRET_KEY")
        if not resolved_secret_key:
            raise RuntimeError("JWT_SECRET_KEY must be set.")
        self.secret_key: str = resolved_secret_key
        if access_token_expire_minutes <= 0:
            raise ValueError("Access token expiration must be positive.")
        self.access_token_expire_minutes = access_token_expire_minutes

    @staticmethod
    def hash_password(password: str) -> str:
        return password_hash.hash(password)

    @staticmethod
    def verify_password(password: str, password_hash_value: str) -> bool:
        return password_hash.verify(password, password_hash_value)

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await self.users.get_by_email(email)
        if user is None or not self.verify_password(password, user.password_hash):
            return None
        return user

    def create_access_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": expires_at,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)

    def decode_access_token(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[JWT_ALGORITHM],
                options={"require": ["exp", "iat", "sub"]},
            )
            if payload.get("type") != "access":
                raise InvalidAccessTokenError("Invalid access token type.")
            return UUID(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError("Invalid access token.") from error

    async def get_current_user(self, token: str) -> User | None:
        user_id = self.decode_access_token(token)
        return await self.users.get_by_id(user_id)