from uuid import UUID

from ..models.user import User
from ..repositories.user import UserRepository


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def get_by_email(self, email: str) -> User | None:
        return await self.repository.get_by_email(email)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.repository.get_by_id(user_id)

    async def create_user(self, email: str, password_hash: str) -> User:
        return await self.repository.create(email, password_hash)