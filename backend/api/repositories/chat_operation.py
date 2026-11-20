from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat_operation import ChatOperation, ChatOperationStatus


class ChatOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        operation_id: UUID,
        *,
        lock: bool = False,
    ) -> ChatOperation | None:
        statement = (
            select(ChatOperation)
            .where(ChatOperation.id == operation_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_by_key(
        self,
        session_id: UUID,
        operation_key: str,
        *,
        lock: bool = False,
    ) -> ChatOperation | None:
        statement = (
            select(ChatOperation)
            .where(
                ChatOperation.session_id == session_id,
                ChatOperation.operation_key == operation_key,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_active_processing(
        self,
        session_id: UUID,
        *,
        exclude_operation_key: str | None = None,
    ) -> ChatOperation | None:
        statement = (
            select(ChatOperation)
            .where(
                ChatOperation.session_id == session_id,
                ChatOperation.status == ChatOperationStatus.PROCESSING.value,
            )
            .order_by(ChatOperation.session_generation.desc())
            .execution_options(populate_existing=True)
        )
        if exclude_operation_key is not None:
            statement = statement.where(
                ChatOperation.operation_key != exclude_operation_key
            )
        return await self.session.scalar(statement)

    async def get_latest_generation(self, session_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.coalesce(func.max(ChatOperation.session_generation), 0))
            .where(ChatOperation.session_id == session_id)
        )
        return int(latest or 0)

    async def create(
        self,
        *,
        session_id: UUID,
        operation_key: str,
        user_message_id: UUID,
        session_generation: int,
    ) -> ChatOperation:
        now = datetime.now(UTC)
        operation = ChatOperation(
            session_id=session_id,
            operation_key=operation_key,
            status=ChatOperationStatus.PROCESSING.value,
            attempt=1,
            session_generation=session_generation,
            user_message_id=user_message_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(operation)
        await self.session.flush()
        return operation
