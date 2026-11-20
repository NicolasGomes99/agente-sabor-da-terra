from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.agents.schemas import ConversationTurn
from api.config import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RAG_SEMANTIC_TOP_K,
    get_embedding_dimensions,
    get_embedding_model,
    get_rag_semantic_top_k,
)
from api.rag import (
    DeterministicHashEmbeddingClient,
    DocumentExtractionError,
    EmbeddingGenerationError,
    GeminiEmbeddingClient,
    build_contextual_query,
    discover_facepe_documents,
    extract_csv_records,
    extract_document_chunks,
    extract_text_chunks,
    is_indexable_document,
    l2_normalize,
)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def test_discover_facepe_documents_finds_20_txt_and_5_csv() -> None:
    files = discover_facepe_documents(DATA_DIR)
    txt_files = [rel for rel, path in files if path.suffix.lower() == ".txt"]
    csv_files = [rel for rel, path in files if path.suffix.lower() == ".csv"]

    assert len(txt_files) == 20
    assert len(csv_files) == 5
    assert len(files) == 25
    assert "LEIA-ME.txt" not in txt_files
    assert all(not rel.endswith(".json") for rel, _ in files)


def test_is_indexable_document_accepts_only_txt_and_csv() -> None:
    assert is_indexable_document("contrato_pnae.txt") is True
    assert is_indexable_document("FINANCEIRO.CSV") is True
    assert is_indexable_document("certificado.pdf") is False
    assert is_indexable_document("foto.png") is False
    assert is_indexable_document("sem_extensao") is False


def test_extract_text_chunks_preserves_header_context_on_long_contract_and_inspection() -> None:
    pnae_path = DATA_DIR / "contratos" / "contrato_pnae_garanhuns.txt"
    pnae_chunks = extract_text_chunks(
        pnae_path.read_bytes(),
        filename=pnae_path.name,
        max_chars=1400,
    )
    assert len(pnae_chunks) >= 2
    assert [c.chunk_index for c in pnae_chunks] == list(range(len(pnae_chunks)))
    assert [c.chunk_key for c in pnae_chunks] == [f"chunk:{i}" for i in range(len(pnae_chunks))]
    for chunk in pnae_chunks:
        assert "contrato_pnae_garanhuns.txt" in chunk.content
        assert "PNAE" in chunk.content
        assert chunk.record_id is None
        assert chunk.record_fields is None
    assert any("DAP ou CAF" in chunk.content for chunk in pnae_chunks)

    # Certificado de P001 deve preservar produtora, validade e produtos cobertos
    cert_path = DATA_DIR / "certificacoes" / "cert_organica_maria_silva_P001.txt"
    cert_chunks = extract_text_chunks(
        cert_path.read_bytes(),
        filename=cert_path.name,
        max_chars=1400,
    )
    assert cert_chunks
    for chunk in cert_chunks:
        assert "15/06/2027" in chunk.content
        assert "Maria das Graças" in chunk.content
    assert any("Goiaba" in chunk.content and "Acerola" in chunk.content for chunk in cert_chunks)


def test_extract_text_chunks_rejects_empty_or_invalid_utf8() -> None:
    with pytest.raises(DocumentExtractionError):
        extract_text_chunks(b"   \n\t ", filename="vazio.txt")
    with pytest.raises(DocumentExtractionError):
        extract_text_chunks(b"\xff\xfe\x00invalid", filename="corrompido.txt")
    with pytest.raises(DocumentExtractionError):
        extract_document_chunks(b"%PDF-1.7", filename="arquivo.pdf")


def test_extract_csv_records_matches_exact_facepe_counts_and_preserves_verbatim_values() -> None:
    expected_counts = {
        "financeiro.csv": 30,
        "lotes.csv": 20,
        "produtores.csv": 18,
        "sazonalidade.csv": 50,
        "tabela_precos_outubro_2026.csv": 53,
    }
    for filename, expected_count in expected_counts.items():
        records = extract_csv_records((DATA_DIR / filename).read_bytes(), filename=filename)
        assert len(records) == expected_count
        assert len({r.record_id for r in records}) == expected_count
        assert all(r.record_fields is not None for r in records)

    # Verifica preservação verbatim de LOT-2026-0094 e LOT-2026-0099 ("40 maços (kg)")
    lot_records = {
        r.record_id: r
        for r in extract_csv_records((DATA_DIR / "lotes.csv").read_bytes(), filename="lotes.csv")
    }
    lot_94 = lot_records["LOT-2026-0094"]
    assert lot_94.record_fields is not None
    assert lot_94.record_fields["produtor_id"] == "P004"
    assert lot_94.record_fields["produto"] == "alface"
    assert lot_94.record_fields["quantidade_kg"] == "300"
    assert lot_94.record_fields["observacao"] == "300 unidades"
    assert lot_94.record_fields["pedido_id"] == "PED-2026-SEP-008"

    lot_99 = lot_records["LOT-2026-0099"]
    assert lot_99.record_fields is not None
    assert lot_99.record_fields["observacao"] == "40 maços (kg)"
    assert "40 maços (kg)" in lot_99.content


def test_extract_csv_records_handles_semicolon_fallback_ids_and_errors() -> None:
    semicolon_csv = b"nome;valor\nItem A;10\nItem B;20\n"
    records = extract_csv_records(semicolon_csv, filename="custom.csv")
    assert [r.record_id for r in records] == ["linha-1", "linha-2"]
    assert records[0].record_fields == {"nome": "Item A", "valor": "10"}

    with pytest.raises(DocumentExtractionError):
        extract_csv_records(b"col1,col2\nonly_one_column\n", filename="quebrado.csv")
    with pytest.raises(DocumentExtractionError):
        extract_csv_records(b"col1,col2\n", filename="sem_dados.csv")


@pytest.mark.asyncio
async def test_deterministic_hash_embedding_client_is_deterministic_and_ranks_relevant_text() -> None:
    client = DeterministicHashEmbeddingClient(dimensions=128)
    v1 = await client.embed_query("certificação orgânica de mel silvestre")
    v2 = await client.embed_query("certificação orgânica de mel silvestre")
    assert v1 == v2
    assert len(v1) == 128

    doc_vecs = await client.embed_documents(
        [
            "Certificação orgânica de mel silvestre válida até março de 2027.",
            "Contrato de entrega de macaxeira e inhame no depósito central.",
        ]
    )
    sim_relevant = sum(a * b for a, b in zip(v1, doc_vecs[0], strict=True))
    sim_irrelevant = sum(a * b for a, b in zip(v1, doc_vecs[1], strict=True))
    assert sim_relevant > sim_irrelevant


@pytest.mark.asyncio
async def test_gemini_embedding_client_batches_normalizes_and_wraps_errors() -> None:
    fake_sdk = Mock()

    def fake_embed_content(*, model: str, contents: list[str], config: object) -> object:
        assert model == "gemini-embedding-001"
        assert getattr(config, "output_dimensionality", None) == 4
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[3.0, 4.0, 0.0, 0.0]) for _ in contents
            ]
        )

    fake_sdk.models.embed_content.side_effect = fake_embed_content
    client = GeminiEmbeddingClient(
        model="gemini-embedding-001",
        dimensions=4,
        batch_size=2,
        client=fake_sdk,
    )

    vectors = await client.embed_documents(["doc 1", "doc 2", "doc 3"])
    assert len(vectors) == 3
    assert fake_sdk.models.embed_content.call_count == 2
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0, 0.0])

    query_vec = await client.embed_query("consulta")
    assert query_vec == pytest.approx([0.6, 0.8, 0.0, 0.0])

    fake_sdk.models.embed_content.side_effect = RuntimeError("quota exceeded")
    with pytest.raises(EmbeddingGenerationError):
        await client.embed_query("falha")

    # Valida retry automático em 429 RESOURCE_EXHAUSTED respeitando retryDelay
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    attempts = 0

    def flaky_embed(*, model: str, contents: list[str], config: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 12.5s.")
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[1.0, 0.0, 0.0, 0.0]) for _ in contents]
        )

    fake_sdk.models.embed_content.side_effect = flaky_embed
    retry_client = GeminiEmbeddingClient(
        model="gemini-embedding-001",
        dimensions=4,
        client=fake_sdk,
        max_rate_limit_retries=2,
        sleep_fn=fake_sleep,
    )
    recovered = await retry_client.embed_query("consulta apos 429")
    assert recovered == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert slept == [13.5]


def test_l2_normalize_and_rag_config_getters(monkeypatch: pytest.MonkeyPatch) -> None:
    assert l2_normalize([3.0, 4.0]) == pytest.approx([0.6, 0.8])
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]

    monkeypatch.delenv("GEMINI_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("RAG_SEMANTIC_TOP_K", raising=False)
    assert get_embedding_model() == DEFAULT_EMBEDDING_MODEL
    assert get_embedding_dimensions() == DEFAULT_EMBEDDING_DIMENSIONS
    assert get_rag_semantic_top_k() == DEFAULT_RAG_SEMANTIC_TOP_K

    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "   ")
    with pytest.raises(RuntimeError):
        get_embedding_model()

    monkeypatch.setenv("GEMINI_EMBEDDING_DIMENSIONS", "0")
    with pytest.raises(RuntimeError):
        get_embedding_dimensions()

    monkeypatch.setenv("RAG_SEMANTIC_TOP_K", "0")
    with pytest.raises(RuntimeError):
        get_rag_semantic_top_k()


def test_build_contextual_query_inherits_entities_on_follow_up() -> None:
    history = [
        ConversationTurn(
            role="user",
            content="Qual a origem do lote LOT-2026-0094 do produtor P004?",
        ),
        ConversationTurn(
            role="model",
            content="O lote LOT-2026-0094 foi fornecido por P004 com alface.",
        ),
    ]
    enriched, ids = build_contextual_query(
        "E qual a temperatura de transporte desse lote?",
        history,
    )
    assert "LOT-2026-0094" in ids["lots"]
    assert "P004" in ids["producers"]
    assert "Contexto recente da conversa:" in enriched
