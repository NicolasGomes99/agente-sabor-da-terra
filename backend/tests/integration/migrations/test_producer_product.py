import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio(loop_scope="function")
INSERT_ASSOCIATION = text(
    "INSERT INTO producer_products (producer_id, product_id) VALUES (:producer_id, :product_id)"
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
        url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        await run_alembic("upgrade", "head")
        engine = create_async_engine(url)
        try:
            yield engine
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def references(migrated_engine: AsyncEngine) -> tuple[UUID, UUID]:
    producer_id, product_id = uuid4(), uuid4()
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO producers (id, code, name, cpf, active) "
                 "VALUES (:id, 'P001', 'Ana Silva', '01234567890', true)"),
            {"id": producer_id},
        )
        await connection.execute(
            text("INSERT INTO products (id, name) VALUES (:id, 'Alface')"),
            {"id": product_id},
        )
    return producer_id, product_id


async def test_producer_product_migration_upgrade_persists_associations(
    migrated_engine: AsyncEngine, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    other_producer_id, other_product_id = uuid4(), uuid4()
    expected = {
        (producer_id, product_id), (producer_id, other_product_id),
        (other_producer_id, product_id),
    }
    async with migrated_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO producers (id, code, name, cpf, active) "
                 "VALUES (:id, 'P002', 'João Silva', '12345678901', false)"),
            {"id": other_producer_id},
        )
        await connection.execute(
            text("INSERT INTO products (id, name) VALUES (:id, 'Coentro')"),
            {"id": other_product_id},
        )
        await connection.execute(INSERT_ASSOCIATION, [
            {"producer_id": producer, "product_id": product}
            for producer, product in expected
        ])

    async with migrated_engine.connect() as connection:
        rows = await connection.execute(text("SELECT producer_id, product_id FROM producer_products"))
        assert {tuple(row) for row in rows} == expected
    await run_alembic("check")


async def test_producer_product_migration_enforces_constraints(
    migrated_engine: AsyncEngine, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    association = {"producer_id": producer_id, "product_id": product_id}
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_ASSOCIATION, association)

    for candidate in (
        association,
        {**association, "producer_id": uuid4()},
        {**association, "product_id": uuid4()},
    ):
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(INSERT_ASSOCIATION, candidate)

    for statement, record_id in (
        (text("DELETE FROM producers WHERE id = :id"), producer_id),
        (text("DELETE FROM products WHERE id = :id"), product_id),
    ):
        with pytest.raises(IntegrityError):
            async with migrated_engine.begin() as connection:
                await connection.execute(statement, {"id": record_id})

    async with migrated_engine.connect() as connection:
        assert (await connection.execute(
            text("SELECT producer_id, product_id FROM producer_products")
        )).one() == references


async def test_producer_product_migration_downgrade_and_reupgrade(
    migrated_engine: AsyncEngine, references: tuple[UUID, UUID],
) -> None:
    producer_id, product_id = references
    association = {"producer_id": producer_id, "product_id": product_id}
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_ASSOCIATION, association)

    await run_alembic("downgrade", "0005_create_producers")
    async with migrated_engine.connect() as connection:
        assert not await connection.run_sync(
            lambda conn: inspect(conn).has_table("producer_products")
        )
        assert (await connection.execute(
            text("SELECT code FROM producers WHERE id = :id"), {"id": producer_id},
        )).scalar_one() == "P001"
        assert (await connection.execute(
            text("SELECT name FROM products WHERE id = :id"), {"id": product_id},
        )).scalar_one() == "Alface"

    await run_alembic("upgrade", "head")
    async with migrated_engine.begin() as connection:
        await connection.execute(INSERT_ASSOCIATION, association)
    async with migrated_engine.connect() as connection:
        assert (await connection.execute(
            text("SELECT producer_id, product_id FROM producer_products")
        )).one() == references
    await run_alembic("check")
