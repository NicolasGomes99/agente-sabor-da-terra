from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, user_id: UUID) -> ChatSession:
        chat = ChatSession(user_id=user_id)
        self.session.add(chat)
        await self.session.flush()
        return chat
    
    async def list_sessions(self, user_id:UUID) -> list[ChatSession]:
        stmt = (select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc()))
        return list((await self.session.scalars(stmt)).all())

    async def get_session(self, session_id: UUID, user_id: UUID) -> ChatSession | None:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
        return await self.session.scalar(stmt)

    async def add_message(self, session_id: UUID, content: str) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, content=content)
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def list_messages(self, session_id: UUID) -> list[ChatMessage]:
        stmt = (select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc()))
        return list((await self.session.scalars(stmt)).all())