from uuid import UUID

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession
from ..repositories.chat import ChatRepository


class SessionNotFoundError(LookupError):
    pass

class ChatService:
    def __init__(self, repository: ChatRepository) -> None:
        self.repository = repository

    async def create_session(self, user_id: UUID) -> ChatSession:
        chat = await self.repository.create_session(user_id)
        await self.repository.session.commit()
        return chat

    async def list_session(self, user_id: UUID) -> list[ChatSession]:
        return await self.repository.list_sessions(user_id)

    async def get_session_with_messages(
            self, session_id: UUID, user_id: UUID
    ) -> tuple[ChatSession, list[ChatMessage]]:
        chat = await self.repository.get_session(session_id, user_id)
        if chat is None:
            raise SessionNotFoundError
        messages = await self.repository.list_messages(chat.id)
        return chat, messages
    
    async def add_message(
            self, session_id: UUID, user_id: UUID, content: str
    ) -> ChatMessage:
        chat = await self.repository.get_session(session_id, user_id)
        if chat is None:
            raise SessionNotFoundError
        message = await self.repository.add_message(chat.id, content)
        await self.repository.session.commit()
        return message
