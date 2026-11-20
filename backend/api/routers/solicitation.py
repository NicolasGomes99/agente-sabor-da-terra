from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..dependencies import (
    get_conversation_service,
    get_current_user,
    get_solicitation_service,
)
from ..schemas.chat import MessageCreate, MessageOut, RecoverableOperationOut
from ..schemas.solicitation import (
    SolicitationCreate,
    SolicitationOut,
    SolicitationSessionOut,
    SolicitationTurnOut,
)
from ..services.conversation import (
    ConversationExecutionError,
    ConversationOperationConflictError,
    ConversationOperationInProgressError,
    ConversationService,
    ConversationSessionNotFoundError,
    ConversationSolicitationFinishedError,
    StaleOperationResultError,
)
from ..services.solicitation import (
    SolicitationNotFoundError,
    SolicitationService,
)

router = APIRouter(
    prefix="/solicitations",
    tags=["solicitations"],
    dependencies=[Depends(get_current_user)],
)

Service = Annotated[SolicitationService, Depends(get_solicitation_service)]
Conversation = Annotated[ConversationService, Depends(get_conversation_service)]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Solicitação não encontrada.",
    )


@router.post(
    "",
    response_model=SolicitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_solicitation(
    payload: SolicitationCreate,
    service: Service,
) -> SolicitationOut:
    solicitation = await service.create_from_analysis(payload)
    return SolicitationOut.model_validate(solicitation)


@router.get("", response_model=list[SolicitationOut])
async def list_solicitations(service: Service) -> list[SolicitationOut]:
    solicitations = await service.list_solicitations()
    return [
        SolicitationOut.model_validate(solicitation)
        for solicitation in solicitations
    ]


@router.get("/{solicitation_id}", response_model=SolicitationOut)
async def get_solicitation(
    solicitation_id: UUID,
    service: Service,
) -> SolicitationOut:
    try:
        solicitation = await service.get_solicitation(solicitation_id)
    except SolicitationNotFoundError as error:
        raise _not_found() from error
    return SolicitationOut.model_validate(solicitation)


@router.post(
    "/{solicitation_id}/open",
    response_model=SolicitationSessionOut,
)
async def open_solicitation_session(
    solicitation_id: UUID,
    service: Service,
    conversation_service: Conversation,
) -> SolicitationSessionOut:
    try:
        solicitation, chat, messages, read_only = (
            await service.open_session(solicitation_id)
        )
    except SolicitationNotFoundError as error:
        raise _not_found() from error

    recoverable = (
        None
        if read_only
        else await conversation_service.get_recoverable_operation(
            chat.id,
            messages=messages,
        )
    )
    return SolicitationSessionOut(
        **SolicitationOut.model_validate(solicitation).model_dump(),
        title=chat.title,
        created_at=chat.created_at,
        read_only=read_only,
        messages=[MessageOut.model_validate(message) for message in messages],
        pending_operation=(
            RecoverableOperationOut.from_operation(recoverable[0], recoverable[1])
            if recoverable is not None
            else None
        ),
    )


@router.post(
    "/{solicitation_id}/messages",
    response_model=SolicitationTurnOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_solicitation_message(
    solicitation_id: UUID,
    payload: MessageCreate,
    conversation_service: Conversation,
) -> SolicitationTurnOut | JSONResponse:
    try:
        turn = await conversation_service.send_triage_chat_message(
            solicitation_id=solicitation_id,
            content=payload.content,
            operation_id=payload.operation_id,
            retry=payload.retry,
        )
    except ConversationSessionNotFoundError as error:
        raise _not_found() from error
    except (
        ConversationSolicitationFinishedError,
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

    assert turn.solicitation is not None
    return SolicitationTurnOut(
        operation_id=turn.operation_id,
        selected_flow=turn.selected_flow,
        user_message=MessageOut.model_validate(turn.user_message),
        assistant_message=MessageOut.model_validate(turn.assistant_message),
        solicitation=SolicitationOut.model_validate(turn.solicitation),
    )


@router.post(
    "/{solicitation_id}/finalize",
    response_model=SolicitationOut,
)
async def finalize_solicitation(
    solicitation_id: UUID,
    service: Service,
) -> SolicitationOut:
    try:
        solicitation = await service.finalize(solicitation_id)
    except SolicitationNotFoundError as error:
        raise _not_found() from error
    return SolicitationOut.model_validate(solicitation)
