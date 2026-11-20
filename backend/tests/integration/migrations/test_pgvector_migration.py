import asyncio
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[3]


async def _run_alembic(*args: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        timeout=60,
    )


@pytest.mark.asyncio
async def test_pgvector_document_indexing_migration_preserves_existing_records_and_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_pgvector_migration",
    ) as postgres:
        async_url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", async_url)

        # Sobe até a revisão anterior (0011_chat_operations)
        await _run_alembic("upgrade", "0011_chat_operations")

        engine = create_async_engine(async_url)
        user_id = uuid4()
        session_id = uuid4()
        message_id = uuid4()
        doc_with_chunk_id = uuid4()
        doc_without_chunk_id = uuid4()
        chunk_id = uuid4()

        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash) "
                        "VALUES (:id, :email, 'hash')"
                    ),
                    {"id": user_id, "email": "mig@example.com"},
                )
                await conn.execute(
                    text(
                        "INSERT INTO chat_sessions (id, user_id, title, created_at) "
                        "VALUES (:id, :uid, 'Conversa', NOW())"
                    ),
                    {"id": session_id, "uid": user_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO chat_messages (id, session_id, role, content, position, created_at) "
                        "VALUES (:id, :sid, 'AGENT', 'Resposta citada', 1, NOW())"
                    ),
                    {"id": message_id, "sid": session_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO documents (id, original_filename, storage_key) "
                        "VALUES (:id1, 'existente.txt', 'key-1'), "
                        "(:id2, 'pendente.txt', 'key-2')"
                    ),
                    {"id1": doc_with_chunk_id, "id2": doc_without_chunk_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO document_chunks (id, document_id, content, embedding, record_id) "
                        "VALUES (:cid, :did, 'Trecho pré-existente', '[0.1,0.2,0.3]', 'REC-1')"
                    ),
                    {"cid": chunk_id, "did": doc_with_chunk_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO citations (message_id, chunk_id) VALUES (:mid, :cid)"
                    ),
                    {"mid": message_id, "cid": chunk_id},
                )

            # Aplica migração 0012_pgvector_document_indexing e valida com alembic check
            await _run_alembic("upgrade", "0012_pgvector_document_indexing")
            await _run_alembic("check")

            async with engine.connect() as conn:
                ext = (
                    await conn.execute(
                        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                    )
                ).scalar_one()
                assert ext == "vector"

                embedding_udt = (
                    await conn.execute(
                        text(
                            "SELECT udt_name FROM information_schema.columns "
                            "WHERE table_name = 'document_chunks' AND column_name = 'embedding'"
                        )
                    )
                ).scalar_one()
                assert embedding_udt == "vector"

                statuses = dict(
                    (
                        await conn.execute(
                            text("SELECT id, processing_status FROM documents")
                        )
                    ).all()
                )
                assert statuses[doc_with_chunk_id] == "indexed"
                assert statuses[doc_without_chunk_id] == "pending"

                citation_count = (
                    await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM citations "
                            "WHERE message_id = :mid AND chunk_id = :cid"
                        ),
                        {"mid": message_id, "cid": chunk_id},
                    )
                ).scalar_one()
                assert citation_count == 1
                dims = (
                    await conn.execute(
                        text(
                            "SELECT vector_dims(embedding) FROM document_chunks WHERE id = :cid"
                        ),
                        {"cid": chunk_id},
                    )
                ).scalar_one()
                assert dims == 3

            # Índice único parcial permite vários source_path=NULL com mesmo nome,
            # mas rejeita duplicata de source_path não nulo.
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO documents (id, original_filename, storage_key, source_path) "
                        "VALUES (:id1, 'dup.txt', 'k-null-1', NULL), "
                        "(:id2, 'dup.txt', 'k-null-2', NULL), "
                        "(:id3, 'financeiro.csv', 'k-src-1', 'financeiro.csv')"
                    ),
                    {"id1": uuid4(), "id2": uuid4(), "id3": uuid4()},
                )

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "INSERT INTO documents (id, original_filename, storage_key, source_path) "
                            "VALUES (:id, 'financeiro.csv', 'k-src-2', 'financeiro.csv')"
                        ),
                        {"id": uuid4()},
                    )

            # Downgrade preserva registros e converte embedding de volta para text
            await _run_alembic("downgrade", "0011_chat_operations")
            async with engine.connect() as conn:
                doc_cols = await conn.run_sync(
                    lambda sync_conn: {
                        col["name"] for col in inspect(sync_conn).get_columns("documents")
                    }
                )
                assert "processing_status" not in doc_cols
                embedding_type = (
                    await conn.execute(
                        text(
                            "SELECT data_type FROM information_schema.columns "
                            "WHERE table_name = 'document_chunks' AND column_name = 'embedding'"
                        )
                    )
                ).scalar_one()
                assert embedding_type == "text"
                preserved_citation = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM citations WHERE chunk_id = :cid"),
                        {"cid": chunk_id},
                    )
                ).scalar_one()
                assert preserved_citation == 1

            # Re-upgrade volta limpo até o head
            await _run_alembic("upgrade", "head")
        finally:
            await engine.dispose()
