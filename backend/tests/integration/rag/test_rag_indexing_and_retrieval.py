import csv
from collections.abc import AsyncIterator, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copytree
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from api import database
from api.agents.consultation.financial import calculate_producer_financial_summary
from api.agents.schemas import ConversationTurn, OrchestratorFlow
from api.app import fastapi_app as app
from api.database import get_db
from api.dependencies import (
    get_document_storage,
    get_embedding_client,
)
from api.load import import_facepe
from api.models.chat_message import ChatMessage, ChatMessageRole
from api.models.chat_session import ChatSession
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk, DocumentProcessingStatus
from api.models.user import User
from api.rag import (
    DeterministicHashEmbeddingClient,
    DocumentIndexingService,
    EmbeddingGenerationError,
    RagRetrievalService,
)
from api.repositories.document import DocumentRepository
from api.repositories.lot import LotRepository
from api.repositories.user import UserRepository
from api.schemas.agent_integration import (
    DocumentRetrievalContext,
    DocumentRetrievalError,
)
from api.services.auth import AuthService
from api.services.producer_summary import ProducerSummaryService
from api.services.user import UserService
from api.storage.local import LocalDocumentStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class _ToggleFailingEmbeddingClient(DeterministicHashEmbeddingClient):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(dimensions=128, model_name="toggle-fake-embedding")
        self.fail = fail

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingGenerationError("Serviço de embeddings indisponível.")
        return await super().embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise EmbeddingGenerationError("Serviço de embeddings indisponível.")
        return await super().embed_query(text)


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "rag-integration-test-secret-key-with-at-least-32-bytes",
    )

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    class _SharedSessionContext:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(
        database,
        "get_session_maker",
        lambda: lambda: _SharedSessionContext(),
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _create_auth_headers(db_session: AsyncSession) -> tuple[User, dict[str, str]]:
    email = f"rag-{uuid4().hex[:8]}@sabordaterra.local"
    password = "secret-password-123"
    user = await UserService(UserRepository(db_session)).create_user(
        email=email,
        password_hash=AuthService.hash_password(password),
    )
    await db_session.commit()
    token = AuthService(UserService(UserRepository(db_session))).create_access_token(
        user.id
    )
    return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_facepe_full_load_idempotency_semantic_and_structured_retrieval(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    # Cobre Critérios 1 a 15 da #52 em PostgreSQL + pgvector com base Facepe completa:
    # - 20 documentos TXT e 5 arquivos CSV preservados integralmente
    # - contagens exatas: financeiro=30, lotes=20, produtores=18, sazonalidade=50, precos=53
    # - repetição da carga preserva IDs de documentos e trechos sem duplicação
    # - busca semântica (certificações, contratos, preços) com pgvector
    # - consulta exata LOT-2026-0094 e LOT-2026-0099 ("40 maços (kg)")
    # - consultas financeiras estruturadas (vendas P001 set/2026, pagamentos P001 out/2026,
    #   pendências em data de referência incluindo períodos anteriores) e integração com #40
    # - consultas estruturadas exaustivas sem truncamento pelo semantic_top_k
    # - acompanhamento conversacional usando histórico da conversa
    storage = LocalDocumentStorage(tmp_path)
    embeddings = DeterministicHashEmbeddingClient(dimensions=128)
    repository = DocumentRepository(db_session)
    indexer = DocumentIndexingService(repository, storage, embeddings)

    first_load = await indexer.load_facepe_documents(DATA_DIR)
    assert first_load.documents_created == 25
    assert first_load.documents_indexed == 25
    assert first_load.documents_failed == 0
    assert first_load.chunks_by_filename["financeiro.csv"] == 30
    assert first_load.chunks_by_filename["lotes.csv"] == 20
    assert first_load.chunks_by_filename["produtores.csv"] == 18
    assert first_load.chunks_by_filename["sazonalidade.csv"] == 50
    assert first_load.chunks_by_filename["tabela_precos_outubro_2026.csv"] == 53

    # Verifica que os arquivos originais foram preservados integralmente no storage
    all_docs_before = await repository.list_all()
    assert len(all_docs_before) == 25
    doc_ids_before = {doc.source_path: doc.id for doc in all_docs_before}
    chunk_ids_before = set(
        (await db_session.scalars(select(DocumentChunk.id))).all()
    )
    lotes_doc = await repository.get_by_source_path("lotes.csv")
    assert lotes_doc is not None
    with storage.open(lotes_doc.storage_key) as reader:
        assert reader.read() == (DATA_DIR / "lotes.csv").read_bytes()

    # Reexecução da carga inicial mantém documentos, IDs e trechos sem duplicação (AC #3)
    second_load = await indexer.load_facepe_documents(DATA_DIR)
    assert second_load.documents_created == 0
    assert second_load.documents_reused == 25
    assert second_load.documents_skipped == 25
    assert second_load.documents_indexed == 0

    all_docs_after = await repository.list_all()
    assert len(all_docs_after) == 25
    assert {doc.source_path: doc.id for doc in all_docs_after} == doc_ids_before
    chunk_ids_after = set(
        (await db_session.scalars(select(DocumentChunk.id))).all()
    )
    assert chunk_ids_after == chunk_ids_before

    # Retrieval com semantic_top_k pequeno (3) para comprovar exaustividade das consultas estruturadas
    retrieval = RagRetrievalService(repository, embeddings, semantic_top_k=5)

    # AC #4: Consulta semântica sobre certificações orgânicas (produtos cobertos + validade)
    cert_hits = await retrieval.semantic_search(
        "certificação orgânica de mel silvestre validade produtos cobertos",
        top_k=5,
    )
    assert any(
        item.document_name.startswith("cert_organica_")
        and "Data de Validade" in item.content
        and "mel" in item.content.lower()
        for item in cert_hits
    )
    assert all(item.source_id and item.document_id and item.document_name for item in cert_hits)

    # AC #5: Consulta sobre exigências contratuais (PNAE)
    contract_hits = await retrieval.semantic_search(
        "exigências obrigatórias do contrato PNAE Garanhuns DAP CAF SIE",
        top_k=5,
    )
    assert any(
        item.document_name == "contrato_pnae_garanhuns.txt"
        for item in contract_hits
    )

    # AC #6: Consulta sobre preços preservando vigência (outubro/2026) e condições
    price_result = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Qual o preço vigente de outubro de 2026 da goiaba paluma extra e desconto de atacado?",
        )
    )
    assert any(
        item.document_name == "tabela_precos_outubro_2026.csv"
        and "goiaba paluma extra" in item.content.lower()
        and item.record_fields is not None
        and item.record_fields["desconto_atacado_pct"] == "10"
        for item in price_result.sources
    )

    # AC #7: Consulta a LOT-2026-0094 recupera registro original completo de lotes.csv
    lot_94_result = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Qual a rastreabilidade do lote LOT-2026-0094?",
        )
    )
    lot_94_items = [
        item for item in lot_94_result.sources if item.record_id == "LOT-2026-0094"
    ]
    assert len(lot_94_items) == 1
    lot_94 = lot_94_items[0]
    assert lot_94.document_name == "lotes.csv"
    assert lot_94.record_fields is not None
    assert lot_94.record_fields["produtor_id"] == "P004"
    assert lot_94.record_fields["produto"] == "alface"
    assert lot_94.record_fields["quantidade_kg"] == "300"
    assert lot_94.record_fields["observacao"] == "300 unidades"
    assert lot_94.record_fields["data_colheita"] == "2026-09-06"
    assert lot_94.record_fields["data_entrega"] == "2026-09-08"
    assert lot_94.record_fields["pedido_id"] == "PED-2026-SEP-008"

    # AC #8: Consulta a LOT-2026-0099 preserva "40 maços (kg)" sem converter nem assumir unidade
    lot_99_items = await retrieval.get_by_record_ids(["LOT-2026-0099"])
    assert len(lot_99_items) == 1
    assert lot_99_items[0].record_fields is not None
    assert lot_99_items[0].record_fields["observacao"] == "40 maços (kg)"
    assert "40 maços (kg)" in lot_99_items[0].content

    # AC #9: Consulta estruturada das vendas de P001 em setembro de 2026
    p001_sales_sep = await retrieval.query_financial_records(
        producer_id="P001",
        date_field="data",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )
    assert [item.record_id for item in p001_sales_sep] == [
        "FIN-2026-001",
        "FIN-2026-002",
        "FIN-2026-015",
    ]

    # AC #10: Consulta estruturada dos pagamentos registrados de P001 em outubro de 2026
    p001_payments_oct = await retrieval.query_financial_records(
        producer_id="P001",
        date_field="data_pagamento",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
    )
    assert [item.record_id for item in p001_payments_oct] == [
        "FIN-2026-001",
        "FIN-2026-002",
    ]

    # AC #11: Pendências na data de referência incluem períodos anteriores e excluem outros produtores
    p003_oct_with_prior_pending = await retrieval.query_financial_records(
        producer_id="P003",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        reference_date=date(2026, 10, 31),
        include_pending_as_of_reference=True,
    )
    assert {item.record_id for item in p003_oct_with_prior_pending} == {
        "FIN-2026-013",
        "FIN-2026-014",
    }
    assert all(
        item.record_fields is not None and item.record_fields["produtor_id"] == "P003"
        for item in p003_oct_with_prior_pending
    )

    # Integração com a ferramenta determinística da #40 sobre os registros recuperados
    p001_sep_context = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Gerar resumo financeiro do produtor P001 em setembro de 2026",
            producer_id="P001",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            financial_reference_date=date(2026, 9, 30),
        )
    )
    assert p001_sep_context.financial_records is not None
    calc = calculate_producer_financial_summary(
        "P001",
        financial_records=p001_sep_context.financial_records,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        reference_date=date(2026, 9, 30),
    )
    assert calc.has_any_records is True
    assert calc.sales_in_period.total_amount == Decimal("1090.00")
    assert calc.registered_payments_in_period.total_amount == Decimal("150.00")
    assert calc.pending_upcoming.total_amount == Decimal("940.00")

    # AC #12: Consultas estruturadas são exaustivas mesmo acima de semantic_top_k=5
    all_financial = await retrieval.query_structured_records(document_name="financeiro.csv")
    all_seasonality = await retrieval.query_structured_records(document_name="sazonalidade.csv")
    all_prices = await retrieval.query_structured_records(
        document_name="tabela_precos_outubro_2026.csv"
    )
    assert len(all_financial) == 30
    assert len(all_seasonality) == 50
    assert len(all_prices) == 53

    # AC #14: Consulta de acompanhamento usa o histórico da conversa
    followup_lot = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="E qual a temperatura de transporte desse lote?",
            history=[
                ConversationTurn(
                    role="user",
                    content="Qual a origem do lote LOT-2026-0094?",
                ),
                ConversationTurn(
                    role="model",
                    content="O lote LOT-2026-0094 é de alface da produtora P004.",
                ),
            ],
        )
    )
    assert any(item.record_id == "LOT-2026-0094" for item in followup_lot.sources)

    followup_cert = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="E qual é a data de validade dela?",
            history=[
                ConversationTurn(
                    role="user",
                    content="Quais produtos constam na certificação orgânica de P001?",
                ),
                ConversationTurn(
                    role="model",
                    content="A certificação de P001 cobre goiaba, acerola e manga.",
                ),
            ],
        )
    )
    assert any(
        item.document_name == "cert_organica_maria_silva_P001.txt"
        for item in followup_cert.sources
    )


@pytest.mark.asyncio
async def test_retrieval_distinguishes_empty_results_from_execution_failure(
    db_session: AsyncSession,
) -> None:
    # Critério 15 da #52: base vazia retorna vazio; erro do embedding levanta DocumentRetrievalError.
    repository = DocumentRepository(db_session)
    toggle_embeddings = _ToggleFailingEmbeddingClient(fail=False)
    retrieval = RagRetrievalService(repository, toggle_embeddings)

    empty = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Consulta sem nenhum documento cadastrado",
        )
    )
    assert empty.sources == []
    assert empty.financial_records is None

    toggle_embeddings.fail = True
    with pytest.raises(DocumentRetrievalError):
        await retrieval.retrieve_sources(
            DocumentRetrievalContext(
                session_id=uuid4(),
                query_text="Consulta quando serviço de embeddings falha",
            )
        )


@pytest.mark.asyncio
async def test_document_upload_same_name_failure_retry_cited_reprocess_and_delete(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    # Critérios 16, 17, 18, 19 e 20 da #52:
    # - upload de TXT e CSV pela API fica disponível para consulta após indexação
    # - dois documentos diferentes com o mesmo nome ficam armazenados e indexados separadamente
    # - falha no processamento não expõe dados parciais e nova tentativa conclui sem duplicação
    # - reprocessamento preserva trechos vinculados a citações existentes
    # - exclusão sem citações remove trechos da base consultável; documento citado segue bloqueado (409)
    user, headers = await _create_auth_headers(db_session)
    storage = LocalDocumentStorage(tmp_path)
    toggle_embeddings = _ToggleFailingEmbeddingClient(fail=False)

    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_client] = lambda: toggle_embeddings

    repository = DocumentRepository(db_session)
    retrieval = RagRetrievalService(repository, toggle_embeddings, semantic_top_k=10)

    # AC #16 + #17: Dois documentos TXT diferentes com o MESMO nome + um CSV
    up1 = await api_client.post(
        "/documents",
        headers=headers,
        files={
            "file": (
                "relatorio_safra.txt",
                b"Relatorio Safra Melao 2026: producao estimada de 12 toneladas em Petrolina.",
                "text/plain",
            )
        },
    )
    assert up1.status_code == 201
    doc1_id = UUID(up1.json()["id"])

    up2 = await api_client.post(
        "/documents",
        headers=headers,
        files={
            "file": (
                "relatorio_safra.txt",
                b"Relatorio Safra Abacaxi 2026: producao estimada de 9 toneladas em Lajedo.",
                "text/plain",
            )
        },
    )
    assert up2.status_code == 201
    doc2_id = UUID(up2.json()["id"])
    assert doc1_id != doc2_id

    up_csv = await api_client.post(
        "/documents",
        headers=headers,
        files={
            "file": (
                "lotes_extras.csv",
                b"lote_id,produto,observacao\nLOT-EXTRA-01,maracuja,25 caixas\n",
                "text/csv",
            )
        },
    )
    assert up_csv.status_code == 201

    melao_hits = await retrieval.semantic_search("producao melao Petrolina")
    assert any(item.document_id == str(doc1_id) for item in melao_hits)
    abacaxi_hits = await retrieval.semantic_search("producao abacaxi Lajedo")
    assert any(item.document_id == str(doc2_id) for item in abacaxi_hits)
    extra_lot = await retrieval.get_by_record_ids(["LOT-EXTRA-01"])
    assert len(extra_lot) == 1
    assert extra_lot[0].record_fields == {
        "lote_id": "LOT-EXTRA-01",
        "produto": "maracuja",
        "observacao": "25 caixas",
    }

    # AC #18: Falha no processamento não deixa dados parciais disponíveis; retry conclui sem duplicar
    toggle_embeddings.fail = True
    up_fail = await api_client.post(
        "/documents",
        headers=headers,
        files={
            "file": (
                "norma_transporte.txt",
                b"Norma de transporte refrigerado: manter laticinios entre 2C e 6C.",
                "text/plain",
            )
        },
    )
    assert up_fail.status_code == 201
    failed_doc_id = UUID(up_fail.json()["id"])

    failed_list = await api_client.get("/documents/indexing?status=failed", headers=headers)
    assert failed_list.status_code == 200
    assert [row["id"] for row in failed_list.json()] == [str(failed_doc_id)]
    assert failed_list.json()[0]["chunk_count"] == 0

    # Não aparece na busca enquanto está failed
    toggle_embeddings.fail = False
    before_retry_hits = await retrieval.semantic_search("transporte refrigerado laticinios 2C 6C")
    assert all(item.document_id != str(failed_doc_id) for item in before_retry_hits)

    # Nova tentativa conclui indexação sem duplicação
    retry_resp = await api_client.post(
        f"/documents/{failed_doc_id}/reindex",
        headers=headers,
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["processing_status"] == DocumentProcessingStatus.INDEXED.value
    assert retry_resp.json()["chunk_count"] == 1

    after_retry_hits = await retrieval.semantic_search("transporte refrigerado laticinios 2C 6C")
    assert any(item.document_id == str(failed_doc_id) for item in after_retry_hits)

    # Repetir reindexação não duplica chunks
    retry_again = await api_client.post(
        f"/documents/{failed_doc_id}/reindex",
        headers=headers,
    )
    assert retry_again.status_code == 200
    assert retry_again.json()["chunk_count"] == 1
    assert len(await repository.list_chunks_by_document(failed_doc_id)) == 1

    # AC #19 + #20: Reprocessar documento com citação preserva trecho citado e bloqueia exclusão (409)
    doc1_chunks = await repository.list_chunks_by_document(doc1_id)
    assert len(doc1_chunks) == 1
    cited_chunk_id = doc1_chunks[0].id

    chat_session = ChatSession(user_id=user.id, title="Sessão citação RAG")
    db_session.add(chat_session)
    await db_session.flush()
    chat_msg = ChatMessage(
        session_id=chat_session.id,
        role=ChatMessageRole.AGENT,
        content="Segundo o relatório da safra de melão...",
        position=1,
    )
    db_session.add(chat_msg)
    await db_session.flush()
    db_session.add(Citation(message_id=chat_msg.id, chunk_id=cited_chunk_id))
    await db_session.commit()

    # Simula alteração de chave do trecho no reprocessamento para testar preservação de citado obsoleto
    doc1_chunks[0].chunk_key = "legacy-key-0"
    await db_session.commit()

    reprocess_cited = await api_client.post(
        f"/documents/{doc1_id}/reindex",
        headers=headers,
    )
    assert reprocess_cited.status_code == 200
    assert reprocess_cited.json()["processing_status"] == "indexed"

    # Trecho citado permanece preservado no banco e a citação continua íntegra
    preserved_chunk = await db_session.get(DocumentChunk, cited_chunk_id)
    assert preserved_chunk is not None
    citation_exists = await db_session.scalar(
        select(Citation).where(
            Citation.message_id == chat_msg.id,
            Citation.chunk_id == cited_chunk_id,
        )
    )
    assert citation_exists is not None

    # Exclusão do documento citado permanece bloqueada (409)
    delete_cited = await api_client.delete(f"/documents/{doc1_id}", headers=headers)
    assert delete_cited.status_code == 409

    # AC #20: Exclusão de documento sem citações remove seus trechos da base consultável
    delete_uncited = await api_client.delete(f"/documents/{doc2_id}", headers=headers)
    assert delete_uncited.status_code == 204
    assert await db_session.get(Document, doc2_id) is None
    assert await repository.list_chunks_by_document(doc2_id) == []
    after_delete_hits = await retrieval.semantic_search("producao abacaxi Lajedo")
    assert all(item.document_id != str(doc2_id) for item in after_delete_hits)


@pytest.mark.asyncio
async def test_producer_summary_service_integrates_end_to_end_with_rag_retrieval_service(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    # Integração #52 (RagRetrievalService) + #63 (ProducerSummaryService) sobre a base da FACEPE.
    storage = LocalDocumentStorage(tmp_path)
    embeddings = DeterministicHashEmbeddingClient(dimensions=128)
    repository = DocumentRepository(db_session)
    indexing = DocumentIndexingService(repository, storage, embeddings)
    retrieval = RagRetrievalService(repository, embeddings, semantic_top_k=8)

    await indexing.load_facepe_documents(DATA_DIR)

    with (DATA_DIR / "produtores.csv").open(encoding="utf-8", newline="") as prod_file:
        producers_rows = list(csv.DictReader(prod_file))
    with (DATA_DIR / "lotes.csv").open(encoding="utf-8", newline="") as lots_file:
        lots_rows = list(csv.DictReader(lots_file))
    await import_facepe(db_session, producers_rows, lots_rows)

    summary_service = ProducerSummaryService(LotRepository(db_session), retrieval)
    response = await summary_service.answer_producer_summary(
        "P004",
        session_id=uuid4(),
        reference_date=date(2026, 10, 1),
        period="2026-09",
    )

    assert response.producer_code == "P004"
    assert response.period_start == date(2026, 9, 1)
    assert response.period_end == date(2026, 9, 30)
    assert response.financial.has_any_records is True
    assert [
        (row.product, row.quantity, row.unit, row.delivery_date)
        for row in response.planned_supplies.supplies
    ] == [
        ("alface", Decimal(300), "un", date(2026, 9, 8)),
        ("coentro", Decimal(150), "maços", date(2026, 9, 8)),
    ]
    assert {
        citation.reference_label
        for citation in response.cited_sources
        if citation.document_name == "lotes.csv"
    } == {"LOT-2026-0094", "LOT-2026-0095"}
    assert any(
        citation.document_name == "financeiro.csv"
        for citation in response.cited_sources
    )

    # Integração #52 (RagRetrievalService) + #62 (enriquecimento da triagem com sazonalidade.csv)
    triage_sources = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Precisamos de 50 kg de cajá e 20 kg de queijo coalho para entrega em 10/11/2026.",
            flow=OrchestratorFlow.TRIAGE,
        )
    )
    season_products = {
        (item.record_fields or {}).get("produto")
        for item in triage_sources.sources
        if item.document_name == "sazonalidade.csv"
    }
    assert {"cajá", "queijo coalho"} <= season_products

@pytest.mark.asyncio
async def test_retrieval_preserves_complete_structured_records(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    storage = LocalDocumentStorage(tmp_path)
    embeddings = DeterministicHashEmbeddingClient(dimensions=128)
    repository = DocumentRepository(db_session)

    indexer = DocumentIndexingService(
        repository,
        storage,
        embeddings,
    )

    retrieval = RagRetrievalService(
        repository,
        embeddings,
        semantic_top_k=5,
    )

    await indexer.load_facepe_documents(DATA_DIR)

    # Consulta em linguagem natural sem período previamente estruturado.
    financial_result = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Quais foram as vendas de P001 em setembro de 2026?",
            reference_date=date(2026, 11, 20),
        )
    )

    assert financial_result.financial_records is not None

    financial_ids = {
        item.record_id
        for item in financial_result.financial_records
    }

    assert {
        "FIN-2026-001",
        "FIN-2026-002",
        "FIN-2026-015",
    } <= financial_ids

    assert all(
        item.record_fields is not None
        and item.record_fields["produtor_id"] == "P001"
        for item in financial_result.financial_records
    )

    calculation = calculate_producer_financial_summary(
        "P001",
        financial_records=financial_result.financial_records,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        reference_date=date(2026, 11, 20),
    )

    assert calculation.has_any_records is True

    assert (
        calculation.sales_in_period.total_amount
        == Decimal("1090.00")
    )

    # Recuperação exaustiva por nome de arquivo.
    structured_result = await retrieval.retrieve_sources(
        DocumentRetrievalContext(
            session_id=uuid4(),
            query_text="Liste todos os registros de sazonalidade.csv.",
        )
    )

    seasonality_sources = [
        item
        for item in structured_result.sources
        if item.document_name == "sazonalidade.csv"
    ]

    assert len(seasonality_sources) == 50

    assert len({
        item.source_id
        for item in seasonality_sources
    }) == 50

@pytest.mark.asyncio
async def test_facepe_update_preserves_cited_evidence_and_original_file(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    copytree(DATA_DIR, data_dir)

    storage = LocalDocumentStorage(tmp_path / "storage")
    embeddings = DeterministicHashEmbeddingClient(dimensions=128)
    repository = DocumentRepository(db_session)

    indexer = DocumentIndexingService(
        repository,
        storage,
        embeddings,
    )

    retrieval = RagRetrievalService(
        repository,
        embeddings,
        semantic_top_k=5,
    )

    await indexer.load_facepe_documents(data_dir)

    document = await repository.get_by_source_path("lotes.csv")
    assert document is not None

    document_id = document.id
    original_storage_key = document.storage_key

    file_path = data_dir / "lotes.csv"
    original_bytes = file_path.read_bytes()

    original_chunks = await repository.list_chunks_by_document(
        document_id,
        only_active=True,
    )

    cited_chunk = next(
        chunk
        for chunk in original_chunks
        if chunk.record_id == "LOT-2026-0099"
    )

    unchanged_chunk = next(
        chunk
        for chunk in original_chunks
        if chunk.record_id == "LOT-2026-0094"
    )

    cited_chunk_id = cited_chunk.id
    unchanged_chunk_id = unchanged_chunk.id

    original_content = cited_chunk.content
    original_fields = dict(cited_chunk.record_fields or {})

    # Cria uma citação vinculada à versão original do registro.
    user, _ = await _create_auth_headers(db_session)

    chat_session = ChatSession(
        user_id=user.id,
        title="Teste de preservação de evidência",
    )

    db_session.add(chat_session)
    await db_session.flush()

    message = ChatMessage(
        session_id=chat_session.id,
        role=ChatMessageRole.AGENT,
        content="Consulta sobre o lote LOT-2026-0099.",
        position=1,
    )

    db_session.add(message)
    await db_session.flush()

    message_id = message.id

    db_session.add(
        Citation(
            message_id=message_id,
            chunk_id=cited_chunk_id,
        )
    )

    await db_session.commit()

    # Modifica efetivamente o conteúdo do registro citado.
    assert "40 maços (kg)".encode() in original_bytes

    updated_bytes = original_bytes.replace(
        "40 maços (kg)".encode(),
        "40 maços".encode(),
        1,
    )

    file_path.write_bytes(updated_bytes)

    update_summary = await indexer.load_facepe_documents(data_dir)

    assert update_summary.documents_created == 0
    assert update_summary.documents_reused == 25
    assert update_summary.documents_indexed == 1
    assert update_summary.documents_skipped == 24
    assert update_summary.documents_failed == 0

    # A identidade do documento permanece inalterada.
    updated_document = await repository.get_by_source_path(
        "lotes.csv"
    )

    assert updated_document is not None
    assert updated_document.id == document_id

    assert (
        updated_document.storage_key
        != original_storage_key
    )

    # Ambas as versões do arquivo permanecem no armazenamento.
    with storage.open(original_storage_key) as reader:
        assert reader.read() == original_bytes

    with storage.open(updated_document.storage_key) as reader:
        assert reader.read() == updated_bytes

    # A evidência histórica deve permanecer intacta.
    preserved_chunk = await db_session.get(
        DocumentChunk,
        cited_chunk_id,
    )

    assert preserved_chunk is not None
    assert preserved_chunk.is_active is False
    assert preserved_chunk.content == original_content
    assert preserved_chunk.record_fields == original_fields

    citation = await db_session.scalar(
        select(Citation).where(
            Citation.message_id == message_id,
            Citation.chunk_id == cited_chunk_id,
        )
    )

    assert citation is not None

    # A recuperação deve retornar somente a versão atualizada.
    updated_chunks = await repository.list_chunks_by_document(
        document_id,
        only_active=True,
    )

    assert len(updated_chunks) == 20

    updated_chunk = next(
        chunk
        for chunk in updated_chunks
        if chunk.record_id == "LOT-2026-0099"
    )

    assert updated_chunk.id != cited_chunk_id
    assert updated_chunk.record_fields is not None
    assert updated_chunk.record_fields["observacao"] == "40 maços"

    retrieved = await retrieval.get_by_record_ids(
        ["LOT-2026-0099"]
    )

    assert len(retrieved) == 1
    assert retrieved[0].record_fields is not None
    assert retrieved[0].record_fields["observacao"] == "40 maços"

    # Registros inalterados devem manter seus identificadores.
    assert any(
        chunk.id == unchanged_chunk_id
        for chunk in updated_chunks
    )

    active_ids_before = {
        chunk.id for chunk in updated_chunks
    }

    # Uma nova reindexação não pode duplicar os trechos.
    await indexer.index_document(document_id)

    active_chunks_after = (
        await repository.list_chunks_by_document(
            document_id,
            only_active=True,
        )
    )

    assert {
        chunk.id for chunk in active_chunks_after
    } == active_ids_before

    all_chunks = await repository.list_chunks_by_document(
        document_id
    )

    assert len(all_chunks) == 21