from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_chat_service, get_current_user
from ..models.user import User
from ..schemas.chat import MessageCreate, MessageOut, SessionDetail, SessionOut
from ..services.chat import ChatService, SessionNotFoundError

router = APIRouter(prefix="/chat", tags=["chat"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[ChatService, Depends(get_chat_service)]

def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Session not found."
    )

@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED
)
async def create_session(user: CurrentUser, service: Service) -> SessionOut:
    chat = await service.create_session(user.id)
    return SessionOut.model_validate(chat)

@router.get("/session", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, service: Service) -> list[SessionOut]:
    sessions = await service.list_session(user.id)
    return [SessionOut.model_validate(s) for s in sessions]

@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    user: CurrentUser,
    service: Service,
) -> SessionDetail:
    try:
        chat, messages = await service.get_session_with_messages(
            session_id, user.id
        )
    except SessionNotFoundError as error:
        raise _not_found() from error

    return SessionDetail(
        **SessionOut.model_validate(chat).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages]
    )

@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    session_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    service: Service
) -> MessageOut:
    try: 
        message = await service.add_message(session_id, user.id, payload.content)
    except SessionNotFoundError as error:
        raise _not_found() from error

    return MessageOut.model_validate(message)