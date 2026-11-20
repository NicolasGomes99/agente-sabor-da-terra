import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import OrchestratorRequest, OrchestratorResponse, orchestrate_request
from ..agents.config import PERNAMBUCO_TIMEZONE
from ..models.chat_message import ChatMessage, ChatMessageRole
from ..models.chat_operation import ChatOperation, ChatOperationStatus
from ..models.solicitation import Solicitation, SolicitationStatus
from ..repositories.chat import ChatRepository
from ..repositories.chat_operation import ChatOperationRepository
from ..repositories.document import DocumentRepository
from ..repositories.solicitation import SolicitationRepository
from ..schemas.agent_integration import (
    AgentPreparedResponse,
    DocumentRetrievalContext,
    DocumentSourceProvider,
    PreparedTriageContext,
    RetrievedDocumentSources,
)
from .agent_integration import (
    AgentIntegrationService,
    convert_orchestrator_response,
    document_chunks_to_source_items,
)

DEFAULT_STALE_PROCESSING_SECONDS = 60.0
DEFAULT_IN_FLIGHT_WAIT_SECONDS = 15.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.05


class ConversationSessionNotFoundError(LookupError):
    """Sessão privada ou solicitação não encontrada (ou sem permissão de acesso)."""


class ConversationSolicitationFinishedError(ValueError):
    """Solicitação finalizada não aceita novas mensagens nem alterações pendentes."""


class ConversationOperationConflictError(ValueError):
    """Mesmo operation_id reutilizado com conteúdo diferente na mesma sessão."""


class ConversationOperationInProgressError(ValueError):
    """Já existe um processamento ativo nesta conversa."""


class StaleOperationResultError(ValueError):
    """Resultado atrasado de tentativa anterior descartado para preservar a tentativa vigente."""


class ConversationExecutionError(RuntimeError):
    """Falha na execução ou persistência da resposta do assistente preservando a mensagem do usuário."""

    def __init__(
        self,
        message: str,
        *,
        operation_id: str,
        user_message: ChatMessage,
    ) -> None:
        super().__init__(message)
        self.operation_id = operation_id
        self.user_message = user_message


@runtime_checkable
class AgentOrchestrator(Protocol):
    async def __call__(
        self,
        request: OrchestratorRequest,
    ) -> OrchestratorResponse:
        ...


async def default_agent_orchestrator(
    request: OrchestratorRequest,
) -> OrchestratorResponse:
    """Aciona o ponto de entrada oficial dos agentes reconstruindo contexto do PostgreSQL."""
    return await orchestrate_request(request, session_store=None)


@runtime_checkable
class TriageOriginMetadataProvider(Protocol):
    """Contrato para recuperar metadados originais de EntradaRecebida (#39) pela solicitação."""

    async def get_triage_context(
        self,
        solicitation: Solicitation,
    ) -> PreparedTriageContext:
        ...


class NullTriageOriginMetadataProvider:
    """Provedor padrão enquanto EntradaRecebida (#39) não está acoplada; delega data ao histórico."""

    async def get_triage_context(
        self,
        solicitation: Solicitation,
    ) -> PreparedTriageContext:
        return PreparedTriageContext(solicitation_id=solicitation.id)


class InMemoryTriageOriginMetadataProvider:
    """Provedor em memória para simular EntradaRecebida (#39) nos testes automatizados."""

    def __init__(
        self,
        contexts_by_solicitation_id: dict[UUID, PreparedTriageContext] | None = None,
    ) -> None:
        self._contexts = dict(contexts_by_solicitation_id or {})

    async def get_triage_context(
        self,
        solicitation: Solicitation,
    ) -> PreparedTriageContext:
        existing = self._contexts.get(solicitation.id)
        if existing is None:
            return PreparedTriageContext(solicitation_id=solicitation.id)
        return existing.model_copy(update={"solicitation_id": solicitation.id})


class PersistedDocumentSourceProvider:
    """Provedor temporário que expõe DocumentChunks de teste persistidos até a entrega do RAG (#52)."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        *,
        limit: int = 50,
    ) -> None:
        self.document_repository = document_repository
        self.limit = limit

    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        _ = context
        chunks = await self.document_repository.list_chunks(limit=self.limit)
        if not chunks:
            return RetrievedDocumentSources()
        return RetrievedDocumentSources(
            sources=document_chunks_to_source_items(chunks),
        )


@dataclass(frozen=True)
class ConversationTurnResult:
    operation_id: str
    selected_flow: Literal["triage", "consultation"]
    user_message: ChatMessage
    assistant_message: ChatMessage
    solicitation: Solicitation | None = None


@dataclass(frozen=True)
class _StartedOperation:
    operation_id: UUID
    operation_key: str
    session_id: UUID
    attempt: int
    session_generation: int
    user_message_id: UUID
    user_content: str
    solicitation_id: UUID | None = None


class _OperationWaiterRegistry:
    """Coordena requisições simultâneas com o mesmo (session_id, operation_key) no mesmo processo."""

    def __init__(self) -> None:
        self._events: dict[tuple[UUID, str], asyncio.Event] = {}

    def register(self, key: tuple[UUID, str]) -> asyncio.Event:
        event = asyncio.Event()
        self._events[key] = event
        return event

    def get(self, key: tuple[UUID, str]) -> asyncio.Event | None:
        return self._events.get(key)

    def notify_and_clear(self, key: tuple[UUID, str], event: asyncio.Event) -> None:
        event.set()
        if self._events.get(key) is event:
            self._events.pop(key, None)


_IN_FLIGHT_WAITERS = _OperationWaiterRegistry()


def _normalize_operation_key(operation_id: str | None) -> str:
    if operation_id is None:
        return str(uuid4())
    cleaned = operation_id.strip()
    if not cleaned:
        raise ValueError("operation_id must not be blank.")
    return cleaned


class ConversationService:
    """Serviço conversacional compartilhado pelo chat livre e pelo chat da triagem (#51)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        source_provider: DocumentSourceProvider | None = None,
        triage_origin_provider: TriageOriginMetadataProvider | None = None,
        orchestrator: AgentOrchestrator | None = None,
        clock: Callable[[], datetime] | None = None,
        stale_processing_seconds: float = DEFAULT_STALE_PROCESSING_SECONDS,
        in_flight_wait_seconds: float = DEFAULT_IN_FLIGHT_WAIT_SECONDS,
    ) -> None:
        self.session = session
        self.chat_repository = ChatRepository(session)
        self.solicitation_repository = SolicitationRepository(session)
        self.operation_repository = ChatOperationRepository(session)
        self.agent_integration = AgentIntegrationService(
            self.chat_repository,
            source_provider=source_provider,
        )
        self.triage_origin_provider: TriageOriginMetadataProvider = (
            triage_origin_provider or NullTriageOriginMetadataProvider()
        )
        self.orchestrator: AgentOrchestrator = orchestrator or default_agent_orchestrator
        self._clock = clock or (lambda: datetime.now(PERNAMBUCO_TIMEZONE))
        self.stale_processing_seconds = stale_processing_seconds
        self.in_flight_wait_seconds = in_flight_wait_seconds

    async def get_recoverable_operation(
        self,
        session_id: UUID,
        *,
        messages: Sequence[ChatMessage] | None = None,
    ) -> tuple[ChatOperation, ChatMessage] | None:
        operation = await self.operation_repository.get_recoverable_for_session(
            session_id
        )
        if operation is None:
            return None

        user_message: ChatMessage | None = None
        if messages is not None:
            user_message = next(
                (msg for msg in messages if msg.id == operation.user_message_id),
                None,
            )
        if user_message is None:
            user_message = await self.chat_repository.get_message_with_citations(
                operation.user_message_id
            )
        if user_message is None:
            return None
        return operation, user_message

    async def send_free_chat_message(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        content: str,
        operation_id: str | None = None,
        retry: bool = False,
    ) -> ConversationTurnResult:
        return await self._execute_conversation_turn(
            content=content,
            operation_id=operation_id,
            retry=retry,
            free_chat_session_id=session_id,
            free_chat_user_id=user_id,
            solicitation_id=None,
        )

    async def send_triage_chat_message(
        self,
        *,
        solicitation_id: UUID,
        content: str,
        operation_id: str | None = None,
        retry: bool = False,
    ) -> ConversationTurnResult:
        return await self._execute_conversation_turn(
            content=content,
            operation_id=operation_id,
            retry=retry,
            free_chat_session_id=None,
            free_chat_user_id=None,
            solicitation_id=solicitation_id,
        )

    async def _execute_conversation_turn(
        self,
        *,
        content: str,
        operation_id: str | None,
        retry: bool,
        free_chat_session_id: UUID | None,
        free_chat_user_id: UUID | None,
        solicitation_id: UUID | None,
    ) -> ConversationTurnResult:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Message content must not be blank.")
        operation_key = _normalize_operation_key(operation_id)

        started_or_result, waiter_key, waiter_event = await self._phase1_start_or_reuse(
            normalized_content=normalized_content,
            operation_key=operation_key,
            retry=retry,
            free_chat_session_id=free_chat_session_id,
            free_chat_user_id=free_chat_user_id,
            solicitation_id=solicitation_id,
        )
        if isinstance(started_or_result, ConversationTurnResult):
            return started_or_result

        started = started_or_result
        assert waiter_key is not None and waiter_event is not None

        try:
            try:
                request, retrieved = await self._prepare_agent_input(started)
                orchestrator_response = await self.orchestrator(request)
                prepared = convert_orchestrator_response(
                    orchestrator_response,
                    provided_sources=retrieved.all_provided_sources,
                    original_request=request,
                )
            except Exception as error:
                is_stale = await self._mark_failed_if_current(
                    started,
                    error_detail=str(error)[:500] or type(error).__name__,
                )
                if is_stale:
                    raise StaleOperationResultError(
                        "Resultado atrasado de uma tentativa anterior foi descartado."
                    ) from error
                user_msg = await self._reload_user_message(started)
                raise ConversationExecutionError(
                    "Não foi possível obter resposta do assistente. Tente novamente.",
                    operation_id=started.operation_key,
                    user_message=user_msg,
                ) from error

            return await self._phase3_commit_result(started, prepared, retrieved)
        finally:
            _IN_FLIGHT_WAITERS.notify_and_clear(waiter_key, waiter_event)

    async def _phase1_start_or_reuse(
        self,
        *,
        normalized_content: str,
        operation_key: str,
        retry: bool,
        free_chat_session_id: UUID | None,
        free_chat_user_id: UUID | None,
        solicitation_id: UUID | None,
    ) -> tuple[
        ConversationTurnResult | _StartedOperation,
        tuple[UUID, str] | None,
        asyncio.Event | None,
    ]:
        wait_target_session_id: UUID | None = None

        try:
            session_id, solicitation = await self._lock_and_validate_target(
                free_chat_session_id=free_chat_session_id,
                free_chat_user_id=free_chat_user_id,
                solicitation_id=solicitation_id,
            )

            existing = await self.operation_repository.get_by_key(
                session_id,
                operation_key,
                lock=True,
            )
            latest_generation = await self.operation_repository.get_latest_generation(
                session_id
            )

            if existing is not None:
                existing_user_msg = await self.chat_repository.get_message_with_citations(
                    existing.user_message_id
                )
                if existing_user_msg is None:
                    await self.session.rollback()
                    raise ConversationExecutionError(
                        "Mensagem original da operação não encontrada.",
                        operation_id=operation_key,
                        user_message=ChatMessage(
                            session_id=session_id,
                            role=ChatMessageRole.USER,
                            content=normalized_content,
                            position=0,
                        ),
                    )
                if existing_user_msg.content != normalized_content:
                    await self.session.rollback()
                    raise ConversationOperationConflictError(
                        "O identificador da operação já foi utilizado com outra mensagem."
                    )

                if existing.status == ChatOperationStatus.COMPLETED.value:
                    result = await self._load_completed_result(
                        existing,
                        user_message=existing_user_msg,
                        solicitation=solicitation,
                    )
                    await self.session.commit()
                    return result, None, None

                if existing.session_generation < latest_generation:
                    await self.session.rollback()
                    raise StaleOperationResultError(
                        "Esta operação foi substituída por uma interação mais recente "
                        "na conversa e não pode mais ser reexecutada."
                    )

                other_active = await self.operation_repository.get_active_processing(
                    session_id,
                    exclude_operation_key=operation_key,
                    lock=True,
                )
                if other_active is not None:
                    if not self._is_stale_processing(other_active):
                        await self.session.rollback()
                        raise ConversationOperationInProgressError(
                            "Já existe uma resposta em processamento nesta conversa. "
                            "Aguarde a conclusão antes de tentar novamente."
                        )
                    other_active.status = ChatOperationStatus.FAILED.value
                    other_active.error_detail = (
                        "Substituída por operação mais recente."
                    )
                    other_active.updated_at = datetime.now(UTC)

                if (
                    existing.status == ChatOperationStatus.PROCESSING.value
                    and not retry
                ):
                    wait_target_session_id = session_id
                    await self.session.commit()
                else:
                    # Nova tentativa da operação vigente: reutiliza a mensagem original
                    # e preserva session_generation, incrementando apenas attempt.
                    existing.attempt += 1
                    existing.status = ChatOperationStatus.PROCESSING.value
                    existing.error_detail = None
                    existing.updated_at = datetime.now(UTC)
                    await self.session.flush()

                    started = _StartedOperation(
                        operation_id=existing.id,
                        operation_key=operation_key,
                        session_id=session_id,
                        attempt=existing.attempt,
                        session_generation=existing.session_generation,
                        user_message_id=existing_user_msg.id,
                        user_content=existing_user_msg.content,
                        solicitation_id=solicitation.id if solicitation else None,
                    )
                    waiter_key = (session_id, operation_key)
                    waiter_event = _IN_FLIGHT_WAITERS.register(waiter_key)
                    await self.session.commit()
                    return started, waiter_key, waiter_event
            else:
                other_active = await self.operation_repository.get_active_processing(
                    session_id,
                    exclude_operation_key=operation_key,
                    lock=True,
                )
                if other_active is not None:
                    if not self._is_stale_processing(other_active):
                        await self.session.rollback()
                        raise ConversationOperationInProgressError(
                            "Já existe uma resposta em processamento nesta conversa. "
                            "Aguarde a conclusão antes de enviar outra mensagem."
                        )
                    other_active.status = ChatOperationStatus.FAILED.value
                    other_active.error_detail = (
                        "Substituída por operação mais recente."
                    )
                    other_active.updated_at = datetime.now(UTC)

                user_message = await self.chat_repository.add_message(
                    session_id,
                    normalized_content,
                    role=ChatMessageRole.USER,
                )
                next_generation = latest_generation + 1
                operation = await self.operation_repository.create(
                    session_id=session_id,
                    operation_key=operation_key,
                    user_message_id=user_message.id,
                    session_generation=next_generation,
                )
                started = _StartedOperation(
                    operation_id=operation.id,
                    operation_key=operation_key,
                    session_id=session_id,
                    attempt=operation.attempt,
                    session_generation=operation.session_generation,
                    user_message_id=user_message.id,
                    user_content=user_message.content,
                    solicitation_id=solicitation.id if solicitation else None,
                )
                waiter_key = (session_id, operation_key)
                waiter_event = _IN_FLIGHT_WAITERS.register(waiter_key)
                await self.session.commit()
                return started, waiter_key, waiter_event
        except Exception:
            if wait_target_session_id is None:
                await self.session.rollback()
            raise

        # Requisição simultânea com o mesmo operation_id (retry=False):
        # aguarda a conclusão da tentativa em andamento sem duplicar mensagens nem chamadas ao agente.
        assert wait_target_session_id is not None
        completed = await self._wait_for_in_flight_operation(
            session_id=wait_target_session_id,
            operation_key=operation_key,
            solicitation_id=solicitation_id,
        )
        return completed, None, None

    async def _lock_and_validate_target(
        self,
        *,
        free_chat_session_id: UUID | None,
        free_chat_user_id: UUID | None,
        solicitation_id: UUID | None,
    ) -> tuple[UUID, Solicitation | None]:
        if free_chat_session_id is not None:
            assert free_chat_user_id is not None
            chat = await self.chat_repository.get_session(
                free_chat_session_id,
                free_chat_user_id,
                lock=True,
            )
            if chat is None:
                raise ConversationSessionNotFoundError("Sessão não encontrada.")
            return chat.id, None

        assert solicitation_id is not None
        solicitation = await self.solicitation_repository.get_by_id(
            solicitation_id,
            lock=True,
        )
        if solicitation is None:
            raise ConversationSessionNotFoundError("Solicitação não encontrada.")
        if solicitation.status == SolicitationStatus.FINISHED:
            raise ConversationSolicitationFinishedError(
                "A conversa está finalizada e não aceita novas mensagens."
            )

        chat = await self.solicitation_repository.get_session(
            solicitation.session_id,
            lock=True,
        )
        if chat is None or chat.user_id is not None:
            raise ConversationSessionNotFoundError("Sessão de triagem não encontrada.")

        if solicitation.status == SolicitationStatus.RECEIVED:
            solicitation.status = SolicitationStatus.IN_REVIEW
        return chat.id, solicitation

    def _is_stale_processing(self, operation: ChatOperation) -> bool:
        updated_at = operation.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - updated_at) >= timedelta(
            seconds=self.stale_processing_seconds
        )

    async def _prepare_agent_input(
        self,
        started: _StartedOperation,
    ) -> tuple[OrchestratorRequest, RetrievedDocumentSources]:
        interaction_at = self._clock()
        if started.solicitation_id is None:
            return await self.agent_integration.prepare_free_chat_input(
                started.session_id,
                started.user_content,
                interaction_at=interaction_at,
                exclude_message_id=started.user_message_id,
            )

        solicitation = await self.solicitation_repository.get_by_id(
            started.solicitation_id
        )
        if solicitation is None:
            raise ConversationSessionNotFoundError("Solicitação não encontrada.")

        triage_context = await self.triage_origin_provider.get_triage_context(
            solicitation
        )
        if triage_context.solicitation_id is None:
            triage_context = triage_context.model_copy(
                update={"solicitation_id": solicitation.id}
            )
        return await self.agent_integration.prepare_triage_chat_input(
            started.session_id,
            started.user_content,
            interaction_at=interaction_at,
            triage_context=triage_context,
            exclude_message_id=started.user_message_id,
        )

    async def _wait_for_in_flight_operation(
        self,
        *,
        session_id: UUID,
        operation_key: str,
        solicitation_id: UUID | None,
    ) -> ConversationTurnResult:
        deadline = asyncio.get_running_loop().time() + self.in_flight_wait_seconds
        waiter_key = (session_id, operation_key)

        while True:
            operation = await self.operation_repository.get_by_key(
                session_id,
                operation_key,
            )
            if operation is None:
                raise ConversationOperationInProgressError(
                    "Operação em andamento não encontrada."
                )

            user_msg = await self.chat_repository.get_message_with_citations(
                operation.user_message_id
            )
            if operation.status == ChatOperationStatus.COMPLETED.value:
                solicitation = (
                    await self.solicitation_repository.get_by_id(solicitation_id)
                    if solicitation_id is not None
                    else None
                )
                assert user_msg is not None
                result = await self._load_completed_result(
                    operation,
                    user_message=user_msg,
                    solicitation=solicitation,
                )
                await self.session.commit()
                return result

            latest_generation = await self.operation_repository.get_latest_generation(
                session_id
            )
            if (
                operation.status != ChatOperationStatus.COMPLETED.value
                and operation.session_generation < latest_generation
            ):
                await self.session.commit()
                raise StaleOperationResultError(
                    "Esta operação foi substituída por uma interação mais recente na conversa."
                )

            if operation.status == ChatOperationStatus.FAILED.value:
                await self.session.commit()
                assert user_msg is not None
                raise ConversationExecutionError(
                    "Não foi possível obter resposta do assistente. Tente novamente.",
                    operation_id=operation_key,
                    user_message=user_msg,
                )

            await self.session.commit()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise ConversationOperationInProgressError(
                    "Esta mensagem ainda está em processamento. Aguarde ou tente novamente."
                )

            event = _IN_FLIGHT_WAITERS.get(waiter_key)
            if event is not None:
                try:
                    await asyncio.wait_for(
                        event.wait(),
                        timeout=min(remaining, DEFAULT_POLL_INTERVAL_SECONDS * 4),
                    )
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(min(remaining, DEFAULT_POLL_INTERVAL_SECONDS))

    async def _load_completed_result(
        self,
        operation: ChatOperation,
        *,
        user_message: ChatMessage,
        solicitation: Solicitation | None,
    ) -> ConversationTurnResult:
        if operation.assistant_message_id is None or operation.selected_flow is None:
            raise ConversationExecutionError(
                "Resposta concluída da operação está indisponível.",
                operation_id=operation.operation_key,
                user_message=user_message,
            )
        assistant_message = await self.chat_repository.get_message_with_citations(
            operation.assistant_message_id
        )
        if assistant_message is None:
            raise ConversationExecutionError(
                "Resposta concluída da operação não encontrada.",
                operation_id=operation.operation_key,
                user_message=user_message,
            )
        flow: Literal["triage", "consultation"] = (
            "triage" if operation.selected_flow == "triage" else "consultation"
        )
        return ConversationTurnResult(
            operation_id=operation.operation_key,
            selected_flow=flow,
            user_message=user_message,
            assistant_message=assistant_message,
            solicitation=solicitation,
        )

    async def _phase3_commit_result(
        self,
        started: _StartedOperation,
        prepared: AgentPreparedResponse,
        retrieved: RetrievedDocumentSources,
    ) -> ConversationTurnResult:
        try:
            # Ordem canônica de locks: solicitação -> sessão -> operação
            # (compatível com _lock_and_validate_target e OrderDraftService #10).
            solicitation: Solicitation | None = None
            if started.solicitation_id is not None:
                solicitation = await self.solicitation_repository.get_by_id(
                    started.solicitation_id,
                    lock=True,
                )
                if solicitation is None:
                    await self.session.rollback()
                    raise ConversationSessionNotFoundError(
                        "Solicitação não encontrada."
                    )

            chat = await self.chat_repository.get_session_by_id(
                started.session_id,
                lock=True,
            )
            if chat is None:
                await self.session.rollback()
                raise ConversationSessionNotFoundError("Sessão não encontrada.")

            operation = await self.operation_repository.get_by_id(
                started.operation_id,
                lock=True,
            )
            if operation is None:
                await self.session.rollback()
                raise StaleOperationResultError("Operação não encontrada.")

            latest_generation = await self.operation_repository.get_latest_generation(
                started.session_id
            )
            is_stale = (
                operation.status != ChatOperationStatus.PROCESSING.value
                or operation.attempt != started.attempt
                or operation.session_generation != latest_generation
            )
            if is_stale:
                await self.session.rollback()
                raise StaleOperationResultError(
                    "Resultado atrasado de uma tentativa anterior foi descartado."
                )

            if (
                solicitation is not None
                and solicitation.status == SolicitationStatus.FINISHED
            ):
                operation.status = ChatOperationStatus.FAILED.value
                operation.error_detail = "Solicitação finalizada durante o processamento."
                operation.updated_at = datetime.now(UTC)
                await self.session.commit()
                raise ConversationSolicitationFinishedError(
                    "A conversa está finalizada e não aceita novas mensagens."
                )

            assistant_message = await self.agent_integration.persist_agent_response(
                started.session_id,
                prepared,
                provided_sources=retrieved.all_provided_sources,
                commit=False,
            )

            if (
                solicitation is not None
                and prepared.selected_flow == "triage"
                and prepared.triage is not None
            ):
                solicitation.summary = prepared.triage.summary
                solicitation.request_type = prepared.triage.request_type
                solicitation.urgency = prepared.triage.urgency
                await self.session.flush()

            operation.status = ChatOperationStatus.COMPLETED.value
            operation.assistant_message_id = assistant_message.id
            operation.selected_flow = prepared.selected_flow
            operation.error_detail = None
            operation.updated_at = datetime.now(UTC)
            await self.session.flush()
            await self.session.commit()
        except (
            ConversationSessionNotFoundError,
            ConversationSolicitationFinishedError,
            StaleOperationResultError,
        ):
            raise
        except Exception as error:
            await self.session.rollback()
            await self._mark_failed_if_current(
                started,
                error_detail=str(error)[:500] or type(error).__name__,
            )
            user_msg = await self._reload_user_message(started)
            raise ConversationExecutionError(
                "Não foi possível salvar a resposta do assistente. Tente novamente.",
                operation_id=started.operation_key,
                user_message=user_msg,
            ) from error

        reloaded_user_msg = await self._reload_user_message(started)
        reloaded_assistant_msg = (
            await self.chat_repository.get_message_with_citations(
                assistant_message.id
            )
            or assistant_message
        )
        return ConversationTurnResult(
            operation_id=started.operation_key,
            selected_flow=prepared.selected_flow,
            user_message=reloaded_user_msg,
            assistant_message=reloaded_assistant_msg,
            solicitation=solicitation,
        )

    async def _reload_user_message(
        self,
        started: _StartedOperation,
    ) -> ChatMessage:
        loaded = await self.chat_repository.get_message_with_citations(
            started.user_message_id
        )
        if loaded is not None:
            return loaded
        return ChatMessage(
            id=started.user_message_id,
            session_id=started.session_id,
            role=ChatMessageRole.USER,
            content=started.user_content,
            position=0,
            citations=[],
        )

    async def _mark_failed_if_current(
        self,
        started: _StartedOperation,
        *,
        error_detail: str,
    ) -> bool:
        """Marca a operação como failed apenas se esta tentativa ainda for a vigente. Retorna True se stale."""
        try:
            if started.solicitation_id is not None:
                solicitation = await self.solicitation_repository.get_by_id(
                    started.solicitation_id,
                    lock=True,
                )
                if solicitation is None:
                    await self.session.rollback()
                    return True
            chat = await self.chat_repository.get_session_by_id(
                started.session_id,
                lock=True,
            )
            if chat is None:
                await self.session.rollback()
                return True
            operation = await self.operation_repository.get_by_id(
                started.operation_id,
                lock=True,
            )
            latest_generation = await self.operation_repository.get_latest_generation(
                started.session_id
            )
            if (
                operation is None
                or operation.status != ChatOperationStatus.PROCESSING.value
                or operation.attempt != started.attempt
                or operation.session_generation != latest_generation
            ):
                await self.session.rollback()
                return True

            operation.status = ChatOperationStatus.FAILED.value
            operation.error_detail = error_detail
            operation.updated_at = datetime.now(UTC)
            await self.session.commit()
            return False
        except SQLAlchemyError:
            await self.session.rollback()
            return False
