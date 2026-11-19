import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio(loop_scope="function")


async def run_alembic(*args: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        timeout=60,
    )


@pytest_asyncio.fixture
async def migrated_engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        await run_alembic("upgrade", "head")
        engine = create_async_engine(url)
        try:
            yield engine
        finally:
            await engine.dispose()


async def test_product_migration_upgrade_enforces_constraints(
    migrated_engine: AsyncEngine,
) -> None:
    product_id = uuid4()
    insert = text("INSERT INTO products (id, name) VALUES (:id, :name)")
    async with migrated_engine.begin() as connection:
        await connection.execute(insert, {"id": product_id, "name": "Alface"})

    async with migrated_engine.connect() as connection:
        row = (await connection.execute(
            text("SELECT id, name FROM products WHERE id = :id"), {"id": product_id}
        )).one()
        assert row.id == product_id
        assert row.name == "Alface"

    for name in (None, "", "   ", "\t", "\n", " \t\r\n ", "Alface"):
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(insert, {"id": uuid4(), "name": name})

    async with migrated_engine.begin() as connection:
        await connection.execute(insert, {"id": uuid4(), "name": "Coentro"})
    await run_alembic("check")


async def test_product_migration_downgrade_and_reupgrade(
    migrated_engine: AsyncEngine,
) -> None:
    await run_alembic("downgrade", "0003_add_chat_message_position")
    async with migrated_engine.connect() as connection:
        assert not await connection.run_sync(lambda conn: inspect(conn).has_table("products"))
        assert await connection.run_sync(lambda conn: inspect(conn).has_table("users"))

    await run_alembic("upgrade", "head")
    async with migrated_engine.begin() as connection:
        assert await connection.run_sync(lambda conn: inspect(conn).has_table("products"))
        await connection.execute(
            text("INSERT INTO products (id, name) VALUES (:id, :name)"),
            {"id": uuid4(), "name": "Alface"},
        )
    await run_alembic("check")
