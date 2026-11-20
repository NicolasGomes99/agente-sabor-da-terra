from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..dependencies import (
    get_chat_service,
    get_conversation_service,
    get_current_user,
)
from ..models.user import User
from ..schemas.chat import (
    ChatTurnOut,
    MessageCreate,
    MessageOut,
    RecoverableOperationOut,
    SessionDetail,
    SessionOut,
)
from ..services.chat import ChatService, SessionNotFoundError
from ..services.conversation import (
    ConversationExecutionError,
    ConversationOperationConflictError,
    ConversationOperationInProgressError,
    ConversationService,
    ConversationSessionNotFoundError,
    StaleOperationResultError,
)

router = APIRouter(prefix="/chat", tags=["chat"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[ChatService, Depends(get_chat_service)]
Conversation = Annotated[ConversationService, Depends(get_conversation_service)]

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

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, service: Service) -> list[SessionOut]:
    sessions = await service.list_session(user.id)
    return [SessionOut.model_validate(s) for s in sessions]

@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    user: CurrentUser,
    service: Service,
    conversation_service: Conversation,
) -> SessionDetail:
    try:
        chat, messages = await service.get_session_with_messages(
            session_id, user.id
        )
    except SessionNotFoundError as error:
        raise _not_found() from error

    recoverable = await conversation_service.get_recoverable_operation(
        chat.id,
        messages=messages,
    )
    return SessionDetail(
        **SessionOut.model_validate(chat).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
        pending_operation=(
            RecoverableOperationOut.from_operation(recoverable[0], recoverable[1])
            if recoverable is not None
            else None
        ),
    )

@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatTurnOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    session_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    conversation_service: Conversation,
) -> ChatTurnOut | JSONResponse:
    try:
        turn = await conversation_service.send_free_chat_message(
            session_id=session_id,
            user_id=user.id,
            content=payload.content,
            operation_id=payload.operation_id,
            retry=payload.retry,
        )
    except ConversationSessionNotFoundError as error:
        raise _not_found() from error
    except (
        ConversationOperationConflictError,
        ConversationOperationInProgressError,
        StaleOperationResultError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ConversationExecutionError as error:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "detail": str(error),
                "operation_id": error.operation_id,
                "user_message": MessageOut.model_validate(
                    error.user_message
                ).model_dump(mode="json"),
            },
        )

    return ChatTurnOut(
        operation_id=turn.operation_id,
        selected_flow=turn.selected_flow,
        user_message=MessageOut.model_validate(turn.user_message),
        assistant_message=MessageOut.model_validate(turn.assistant_message),
    )