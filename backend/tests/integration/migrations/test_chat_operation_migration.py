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

OPERATION_REVISION = "0011_chat_operations"
PARENT_REVISION = "0010_chat_agent_metadata"
BACKEND_DIR = Path(__file__).resolve().parents[3]


async def _seed_session_and_message(url: str) -> tuple[UUID, UUID]:
    user_id = uuid4()
    session_id = uuid4()
    message_id = uuid4()
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
                    "VALUES (:id, :user_id, 'Conversa existente', now())"
                ),
                {"id": session_id, "user_id": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO chat_messages "
                    "(id, session_id, role, content, position, created_at) "
                    "VALUES (:id, :session_id, 'USER', 'Mensagem prévia', 1, now())"
                ),
                {"id": message_id, "session_id": session_id},
            )
    finally:
        await engine.dispose()
    return session_id, message_id


async def _get_tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda conn: set(inspect(conn).get_table_names())
            )
    finally:
        await engine.dispose()


async def _verify_operation_constraints(
    url: str,
    session_id: UUID,
    user_message_id: UUID,
) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO chat_operations "
                    "(id, session_id, operation_key, status, attempt, session_generation, "
                    "user_message_id, created_at, updated_at) "
                    "VALUES (:id, :session_id, 'op-1', 'processing', 1, 1, :msg_id, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "session_id": session_id,
                    "msg_id": user_message_id,
                },
            )

        # Duplicar (session_id, operation_key) é bloqueado pela constraint única
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO chat_operations "
                        "(id, session_id, operation_key, status, attempt, session_generation, "
                        "user_message_id, created_at, updated_at) "
                        "VALUES (:id, :session_id, 'op-1', 'processing', 1, 2, :msg_id, now(), now())"
                    ),
                    {
                        "id": uuid4(),
                        "session_id": session_id,
                        "msg_id": user_message_id,
                    },
                )

        # Status inválido é bloqueado pela check constraint
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO chat_operations "
                        "(id, session_id, operation_key, status, attempt, session_generation, "
                        "user_message_id, created_at, updated_at) "
                        "VALUES (:id, :session_id, 'op-invalid', 'unknown', 1, 2, :msg_id, now(), now())"
                    ),
                    {
                        "id": uuid4(),
                        "session_id": session_id,
                        "msg_id": user_message_id,
                    },
                )
    finally:
        await engine.dispose()


def test_chat_operations_migration_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1
    assert OPERATION_REVISION in {
        entry.revision
        for entry in script.walk_revisions(base="base", head=heads[0])
    }

    revision = script.get_revision(OPERATION_REVISION)
    assert revision is not None
    assert revision.down_revision == PARENT_REVISION

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_chat_operations_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, PARENT_REVISION)
        session_id, msg_id = asyncio.run(_seed_session_and_message(url))
        before_tables = asyncio.run(_get_tables(url))
        assert "chat_operations" not in before_tables

        command.upgrade(config, OPERATION_REVISION)
        upgraded_tables = asyncio.run(_get_tables(url))
        assert upgraded_tables == before_tables | {"chat_operations"}
        asyncio.run(_verify_operation_constraints(url, session_id, msg_id))

        command.downgrade(config, PARENT_REVISION)
        downgraded_tables = asyncio.run(_get_tables(url))
        assert downgraded_tables == before_tables

        command.upgrade(config, OPERATION_REVISION)
        reupgraded_tables = asyncio.run(_get_tables(url))
        assert reupgraded_tables == before_tables | {"chat_operations"}
