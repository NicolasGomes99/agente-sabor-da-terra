from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        normalized_email = email.strip().casefold()
        statement = select(User).where(User.email == normalized_email)
        return await self.session.scalar(statement)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def create(self, email: str, password_hash: str) -> User:
        user = User(
            email=email.strip().casefold(),
            password_hash=password_hash,
        )
        self.session.add(user)
        await self.session.flush()
        return user