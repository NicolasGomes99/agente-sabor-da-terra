import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[3]
LEGACY_REVISION = "0004_create_products"
ROLE_REVISION = "0005_chat_message_role_enum"
pytestmark = pytest.mark.asyncio(loop_scope="function")


async def run_alembic(*args: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        timeout=60,
    )


@pytest_asyncio.fixture
async def migration_engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            yield engine
        finally:
            await engine.dispose()


async def seed_messages(engine: AsyncEngine, *roles: str) -> list[tuple[UUID, str, str, int]]:
    user_id, session_id = uuid4(), uuid4()
    messages = []
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'hash')"),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
        await connection.execute(
            text("""
                INSERT INTO chat_sessions (id, user_id, title, created_at)
                VALUES (:id, :user_id, 'Chat', now())
            """),
            {"id": session_id, "user_id": user_id},
        )
        for position, role in enumerate(roles, start=1):
            message_id, content = uuid4(), f"Mensagem {position}"
            await connection.execute(
                text("""
                    INSERT INTO chat_messages (id, session_id, role, content, position, created_at)
                    VALUES (:id, :session_id, :role, :content, :position, now())
                """),
                {
                    "id": message_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "position": position,
                },
            )
            messages.append((message_id, role, content, position))
    return messages


async def read_messages(engine: AsyncEngine) -> list[tuple[UUID, str, str, int]]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT id, role::text, content, position FROM chat_messages ORDER BY position")
        )
        return [
            (message_id, role, content, position)
            for message_id, role, content, position in result
        ]


async def test_chat_message_role_upgrade_converts_legacy_roles(migration_engine: AsyncEngine) -> None:
    await run_alembic("upgrade", LEGACY_REVISION)
    messages = await seed_messages(migration_engine, "user", "assistant")

    await run_alembic("upgrade", ROLE_REVISION)

    assert await read_messages(migration_engine) == [
        (message_id, migrated_role, content, position)
        for (message_id, _, content, position), migrated_role in zip(
            messages, ("USER", "AGENT"), strict=True
        )
    ]
    with pytest.raises(DBAPIError, match="invalid input value for enum chat_message_role"):
        await seed_messages(migration_engine, "UNKNOWN")


async def test_chat_message_role_downgrade_and_reupgrade_preserve_messages(
    migration_engine: AsyncEngine,
) -> None:
    await run_alembic("upgrade", ROLE_REVISION)
    messages = await seed_messages(migration_engine, "USER", "AGENT")

    await run_alembic("downgrade", LEGACY_REVISION)

    async with migration_engine.connect() as connection:
        role_type = (await connection.execute(text("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = current_schema()
                AND table_name = 'chat_messages' AND column_name = 'role'
        """))).one()
    assert role_type == ("character varying", 16)
    assert await read_messages(migration_engine) == [
        (message_id, legacy_role, content, position)
        for (message_id, _, content, position), legacy_role in zip(
            messages, ("user", "assistant"), strict=True
        )
    ]

    await run_alembic("upgrade", ROLE_REVISION)
    assert await read_messages(migration_engine) == messages


async def test_chat_message_role_upgrade_rejects_unknown_legacy_role(
    migration_engine: AsyncEngine,
) -> None:
    await run_alembic("upgrade", LEGACY_REVISION)
    messages = await seed_messages(migration_engine, "unknown")

    with pytest.raises(subprocess.CalledProcessError) as failure:
        await run_alembic("upgrade", ROLE_REVISION)

    assert b'invalid input value for enum chat_message_role: "unknown"' in failure.value.stderr
    async with migration_engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            LEGACY_REVISION
        )
        assert await connection.scalar(text("SELECT to_regtype('chat_message_role')")) is None
    assert await read_messages(migration_engine) == messages
