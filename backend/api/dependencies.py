from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.cloud.storage import Client
from sqlalchemy.ext.asyncio import AsyncSession

from . import database
from .config import (
    get_document_storage_backend,
    get_document_storage_bucket,
    get_document_storage_dir,
)
from .database import get_db
from .models.user import User
from .rag.embeddings import EmbeddingClient, GeminiEmbeddingClient
from .rag.indexing import DocumentIndexingService
from .rag.retrieval import RagRetrievalService
from .repositories.chat import ChatRepository
from .repositories.document import DocumentRepository
from .repositories.lot import LotRepository
from .repositories.order import OrderRepository
from .repositories.order_draft import OrderDraftRepository
from .repositories.producer import ProducerRepository
from .repositories.product import ProductRepository
from .repositories.solicitation import SolicitationRepository
from .repositories.user import UserRepository
from .schemas.agent_integration import DocumentSourceProvider
from .services.agent_integration import AgentIntegrationService
from .services.auth import AuthService, InvalidAccessTokenError
from .services.chat import ChatService
from .services.conversation import (
    AgentOrchestrator,
    ConversationService,
    NullTriageOriginMetadataProvider,
    TriageOriginMetadataProvider,
    default_agent_orchestrator,
)
from .services.document import DocumentService
from .services.lot import LotService
from .services.order import OrderService
from .services.order_draft import OrderDraftService
from .services.producer import ProducerService
from .services.product import ProductService
from .services.solicitation import SolicitationService
from .services.user import UserService
from .storage.base import DocumentStorage
from .storage.gcs import GCSDocumentStorage
from .storage.local import LocalDocumentStorage

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
_gcs_client_lock = Lock()
_gcs_client: Client | None = None


def _get_gcs_client() -> Client:
    global _gcs_client

    with _gcs_client_lock:
        if _gcs_client is None:
            _gcs_client = Client()

        return _gcs_client


def _build_auth_service(session: AsyncSession) -> AuthService:
    user_repository = UserRepository(session)
    user_service = UserService(user_repository)
    return AuthService(user_service)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> AuthService:
    return _build_auth_service(session)


def get_document_storage() -> DocumentStorage:
    if get_document_storage_backend() == "local":
        return LocalDocumentStorage(get_document_storage_dir())

    bucket_name = get_document_storage_bucket()
    return GCSDocumentStorage(_get_gcs_client().bucket(bucket_name))


def get_embedding_client() -> EmbeddingClient:
    return GeminiEmbeddingClient()


def get_document_indexing_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
) -> DocumentIndexingService:
    return DocumentIndexingService(
        DocumentRepository(session),
        storage,
        embedding_client,
    )


def get_document_source_provider(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
) -> DocumentSourceProvider:
    return RagRetrievalService(
        DocumentRepository(session),
        embedding_client,
    )


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    embedding_client: Annotated[
        EmbeddingClient | None, Depends(get_embedding_client)
    ] = None,
) -> DocumentService:
    repository = DocumentRepository(session)
    indexer = (
        DocumentIndexingService(repository, storage, embedding_client)
        if embedding_client is not None
        else None
    )
    return DocumentService(repository, storage, indexer=indexer)


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ChatService:
    return ChatService(ChatRepository(session))


def get_product_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ProductService:
    return ProductService(ProductRepository(session))


def get_producer_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ProducerService:
    return ProducerService(ProducerRepository(session))


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    session_maker = database.get_session_maker()

    try:
        async with session_maker() as session:
            user = await _build_auth_service(session).get_current_user(token)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_order_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db, scope="function"),
    ],
) -> OrderService:
    return OrderService(
        repository=OrderRepository(session),
        product_repository=ProductRepository(session),
    )


def get_lot_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db, scope="function"),
    ],
) -> LotService:
    return LotService(
        repository=LotRepository(session),
        order_repository=OrderRepository(session),
        producer_repository=ProducerRepository(session),
    )


def get_solicitation_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> SolicitationService:
    return SolicitationService(SolicitationRepository(session))


def get_order_draft_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> OrderDraftService:
    return OrderDraftService(
        repository=OrderDraftRepository(session),
        order_service=OrderService(
            OrderRepository(session),
            ProductRepository(session),
        ),
        chat_repository=ChatRepository(session),
        solicitation_repository=SolicitationRepository(session),
    )


def get_triage_origin_metadata_provider() -> TriageOriginMetadataProvider:
    return NullTriageOriginMetadataProvider()


def get_agent_orchestrator() -> AgentOrchestrator:
    return default_agent_orchestrator


def get_agent_integration_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    source_provider: Annotated[
        DocumentSourceProvider | None, Depends(get_document_source_provider)
    ] = None,
) -> AgentIntegrationService:
    return AgentIntegrationService(
        ChatRepository(session),
        source_provider=source_provider,
    )


def get_conversation_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    source_provider: Annotated[
        DocumentSourceProvider, Depends(get_document_source_provider)
    ],
    triage_origin_provider: Annotated[
        TriageOriginMetadataProvider,
        Depends(get_triage_origin_metadata_provider),
    ],
    orchestrator: Annotated[
        AgentOrchestrator, Depends(get_agent_orchestrator)
    ],
) -> ConversationService:
    return ConversationService(
        session,
        source_provider=source_provider,
        triage_origin_provider=triage_origin_provider,
        orchestrator=orchestrator,
    )
