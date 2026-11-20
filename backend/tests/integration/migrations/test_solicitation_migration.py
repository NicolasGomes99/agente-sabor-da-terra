import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command

SOLICITATION_REVISION = "0007_create_solicitations"
PARENT_REVISION = "0005_chat_message_role_enum"
MAIN_REVISION = "0007_chunk_csv_record"
MERGE_REVISION = "0008_merge_triage_main"
BACKEND_DIR = Path(__file__).resolve().parents[3]


async def _snapshot(url: str) -> tuple[set[str], str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda conn: set(inspect(conn).get_table_names())
            )
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert isinstance(revision, str)
            return tables, revision
    finally:
        await engine.dispose()


async def _seed_private_session(url: str) -> tuple[UUID, UUID]:
    user_id, session_id, message_id = uuid4(), uuid4(), uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) "
                    "VALUES (:id, :email, 'hash')"
                ),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_sessions (id, user_id, title, created_at) "
                    "VALUES (:id, :user_id, 'Conversa privada', now())"
                ),
                {"id": session_id, "user_id": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, session_id, role, content, position, created_at) "
                    "VALUES (:id, :session_id, 'USER', 'Mensagem privada', 1, now())"
                ),
                {"id": message_id, "session_id": session_id},
            )
    finally:
        await engine.dispose()
    return user_id, session_id


async def _check_schema(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:

            def read_schema(conn):
                inspector = inspect(conn)
                return (
                    inspector.get_columns("chat_sessions"),
                    inspector.get_columns("solicitations"),
                    inspector.get_pk_constraint("solicitations"),
                    inspector.get_foreign_keys("solicitations"),
                    inspector.get_unique_constraints("solicitations"),
                )

            (
                session_columns,
                solicitation_columns,
                primary_key,
                foreign_keys,
                unique,
            ) = await connection.run_sync(read_schema)

        session_by_name = {column["name"]: column for column in session_columns}
        assert session_by_name["user_id"]["nullable"] is True

        solicitation_by_name = {
            column["name"]: column for column in solicitation_columns
        }
        assert set(solicitation_by_name) == {
            "id",
            "status",
            "summary",
            "request_type",
            "urgency",
            "session_id",
        }
        assert all(
            column["nullable"] is False
            for column in solicitation_by_name.values()
        )
        assert primary_key["constrained_columns"] == ["id"]
        assert any(
            foreign_key["constrained_columns"] == ["session_id"]
            and foreign_key["referred_table"] == "chat_sessions"
            and foreign_key["referred_columns"] == ["id"]
            and foreign_key["options"].get("ondelete") == "RESTRICT"
            for foreign_key in foreign_keys
        )
        assert any(
            item["name"] == "uq_solicitations_session_id"
            and item["column_names"] == ["session_id"]
            for item in unique
        )
    finally:
        await engine.dispose()


async def _check_enum_values(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            status_values = list(
                (
                    await connection.scalars(
                        text(
                            "SELECT enumlabel FROM pg_enum "
                            "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                            "WHERE pg_type.typname = 'solicitation_status' "
                            "ORDER BY enumsortorder"
                        )
                    )
                ).all()
            )
            type_values = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT enumlabel FROM pg_enum "
                            "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                            "WHERE pg_type.typname = 'solicitation_type'"
                        )
                    )
                ).all()
            )
            urgency_values = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT enumlabel FROM pg_enum "
                            "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                            "WHERE pg_type.typname = 'solicitation_urgency'"
                        )
                    )
                ).all()
            )
    finally:
        await engine.dispose()

    assert status_values == ["recebida", "em_analise", "finalizada"]
    assert type_values == {
        "pedido",
        "consulta",
        "oferta",
        "comunicado",
        "nao_identificado",
    }
    assert urgency_values == {"urgente", "normal", "indeterminada"}


async def _insert_triage_session(url: str) -> UUID:
    session_id, message_id = uuid4(), uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO chat_sessions (id, user_id, title, created_at) "
                    "VALUES (:id, NULL, 'Sessão de triagem', now())"
                ),
                {"id": session_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, session_id, role, content, position, created_at) "
                    "VALUES (:id, :session_id, 'USER', 'Mensagem original', 1, now())"
                ),
                {"id": message_id, "session_id": session_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO solicitations "
                    "(id, status, summary, request_type, urgency, session_id) "
                    "VALUES (:id, CAST(:status AS solicitation_status), :summary, "
                    "CAST(:request_type AS solicitation_type), "
                    "CAST(:urgency AS solicitation_urgency), :session_id)"
                ),
                {
                    "id": uuid4(),
                    "status": "recebida",
                    "summary": "Oferta de queijo coalho.",
                    "request_type": "oferta",
                    "urgency": "urgente",
                    "session_id": session_id,
                },
            )
    finally:
        await engine.dispose()
    return session_id


async def _assert_second_solicitation_is_rejected(url: str, session_id: UUID) -> None:
    engine = create_async_engine(url)
    try:
        with pytest.raises(IntegrityError) as error:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO solicitations "
                        "(id, status, summary, request_type, urgency, session_id) "
                        "VALUES (:id, 'recebida'::solicitation_status, "
                        "'Duplicada', 'pedido'::solicitation_type, "
                        "'normal'::solicitation_urgency, :session_id)"
                    ),
                    {"id": uuid4(), "session_id": session_id},
                )
        assert "uq_solicitations_session_id" in str(error.value)
    finally:
        await engine.dispose()


async def _assert_null_owner_is_rejected(url: str) -> None:
    engine = create_async_engine(url)
    try:
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO chat_sessions "
                        "(id, user_id, title, created_at) "
                        "VALUES (:id, NULL, 'Sem titular', now())"
                    ),
                    {"id": uuid4()},
                )
    finally:
        await engine.dispose()


async def _count(url: str, statement: str, parameters: dict | None = None) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(text(statement), parameters or {})
            assert isinstance(result, int)
            return result
    finally:
        await engine.dispose()


async def _enum_type_exists(url: str, name: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(
                text("SELECT to_regtype(:name) IS NOT NULL"),
                {"name": name},
            )
    finally:
        await engine.dispose()


def test_solicitation_migration_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision(
        SOLICITATION_REVISION
    )
    assert revision is not None
    assert revision.down_revision == PARENT_REVISION
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    assert len(heads) == 1
    assert MERGE_REVISION in {
        migration.revision
        for migration in script.walk_revisions(
            base="base",
            head=heads[0],
        )
    }

    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_solicitation_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, PARENT_REVISION)
        user_id, private_session_id = asyncio.run(_seed_private_session(url))
        baseline_tables, current = asyncio.run(_snapshot(url))
        assert current == PARENT_REVISION
        assert "solicitations" not in baseline_tables

        command.upgrade(config, SOLICITATION_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert current == SOLICITATION_REVISION
        assert tables == baseline_tables | {"solicitations"}
        asyncio.run(_check_schema(url))
        asyncio.run(_check_enum_values(url))

        triage_session_id = asyncio.run(_insert_triage_session(url))
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE user_id = :user_id",
                {"user_id": user_id},
            )
        ) == 1
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": private_session_id},
            )
        ) == 1
        asyncio.run(
            _assert_second_solicitation_is_rejected(url, triage_session_id)
        )

        command.downgrade(config, PARENT_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert current == PARENT_REVISION
        assert "solicitations" not in tables
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": private_session_id},
            )
        ) == 1
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": triage_session_id},
            )
        ) == 0
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_messages WHERE session_id = :session_id",
                {"session_id": triage_session_id},
            )
        ) == 0
        assert (
            asyncio.run(_enum_type_exists(url, "solicitation_status")) is False
        )
        asyncio.run(_assert_null_owner_is_rejected(url))

        command.upgrade(config, SOLICITATION_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert current == SOLICITATION_REVISION
        assert tables == baseline_tables | {"solicitations"}
        asyncio.run(_check_schema(url))
        existing_triage_session_id = asyncio.run(_insert_triage_session(url))

        command.upgrade(config, "head")
        tables, current = asyncio.run(_snapshot(url))
        assert current == ScriptDirectory.from_config(config).get_current_head()
        assert {"citations", "document_chunks", "solicitations"} <= tables
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": private_session_id},
            )
        ) == 1
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": existing_triage_session_id},
            )
        ) == 1


def test_full_migration_history_upgrades_from_zero_and_existing_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_full_migration_history",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, "head")
        tables, current = asyncio.run(_snapshot(url))
        assert current == ScriptDirectory.from_config(config).get_current_head()
        assert {
            "users",
            "chat_sessions",
            "chat_messages",
            "documents",
            "document_chunks",
            "citations",
            "solicitations",
        } <= tables
        asyncio.run(_check_schema(url))

        command.downgrade(config, "base")
        command.upgrade(config, MAIN_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert current == MAIN_REVISION
        assert "solicitations" not in tables
        user_id, private_session_id = asyncio.run(_seed_private_session(url))
        command.upgrade(config, "head")

        tables, current = asyncio.run(_snapshot(url))
        assert current == ScriptDirectory.from_config(config).get_current_head()
        assert "solicitations" in tables
        asyncio.run(_check_schema(url))
        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE id = :session_id",
                {"session_id": private_session_id},
            )
        ) == 1

        assert asyncio.run(
            _count(
                url,
                "SELECT count(*) FROM chat_sessions WHERE user_id = :user_id",
                {"user_id": user_id},
            )
        ) == 1
