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
INSERT_PRODUCER = text(
    "INSERT INTO producers "
    "(id, code, name, cpf, active, phone, email, address, municipality) "
    "VALUES (:id, :code, :name, :cpf, :active, :phone, :email, :address, :municipality)"
)


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
        monkeypatch.setenv("DATABASE_URL", postgres.get_connection_url(driver="asyncpg"))
        await run_alembic("upgrade", "head")
        engine = create_async_engine(postgres.get_connection_url(driver="asyncpg"))
        try:
            yield engine
        finally:
            await engine.dispose()


async def test_producer_migration_upgrade_persists_data(
    migrated_engine: AsyncEngine,
) -> None:
    records = [
        {
            "id": uuid4(), "code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True,
            "phone": "81999990000", "email": "ana@example.com", "address": "Rua das Flores, 10",
            "municipality": "Caruaru",
        },
        {
            "id": uuid4(), "code": "P002", "name": "João Silva", "cpf": "12345678901", "active": False,
            "phone": None, "email": None, "address": None, "municipality": None,
        },
    ]
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_PRODUCER, records)

    async with migrated_engine.connect() as connection:
        rows = (await connection.execute(text("SELECT * FROM producers ORDER BY code"))).mappings()
        assert [dict(row) for row in rows] == records
    await run_alembic("check")


async def test_producer_migration_enforces_constraints(
    migrated_engine: AsyncEngine,
) -> None:
    original = {
        "id": uuid4(), "code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True,
        "phone": None, "email": None, "address": None, "municipality": None,
    }
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_PRODUCER, original)

    invalid_values = [(field, None) for field in ("code", "name", "cpf", "active")]
    invalid_values += [
        (field, value)
        for field in ("code", "name", "cpf")
        for value in ("", "   ", "\t", "\n", " \t\r\n ")
    ]
    invalid_values += [(field, original[field]) for field in ("code", "cpf")]
    for field, value in invalid_values:
        candidate = {
            **original, "id": uuid4(), "code": "P002", "cpf": "12345678901", field: value,
        }
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(INSERT_PRODUCER, candidate)


async def test_producer_migration_downgrade_and_reupgrade(
    migrated_engine: AsyncEngine,
) -> None:
    product_id = uuid4()
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO products (id, name) VALUES (:id, :name)"),
            {"id": product_id, "name": "Alface"},
        )

    await run_alembic("downgrade", "0004_create_products")
    async with migrated_engine.connect() as connection:
        assert not await connection.run_sync(lambda conn: inspect(conn).has_table("producers"))
        assert (await connection.execute(
            text("SELECT name FROM products WHERE id = :id"), {"id": product_id},
        )).scalar_one() == "Alface"

    await run_alembic("upgrade", "head")
    producer_id = uuid4()
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_PRODUCER, {
            "id": producer_id, "code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True,
            "phone": None, "email": None, "address": None, "municipality": None,
        })
    async with migrated_engine.connect() as connection:
        assert (await connection.execute(
            text("SELECT code FROM producers WHERE id = :id"), {"id": producer_id},
        )).scalar_one() == "P001"
    await run_alembic("check")
