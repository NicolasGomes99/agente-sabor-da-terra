import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command

ITEM_REVISION = "bedbc9f628aa"
BACKEND_DIR = Path(__file__).resolve().parents[3]


async def snapshot(url: str) -> tuple[set[str], str, list[dict]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda conn: set(inspect(conn).get_table_names())
            )
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            result = await connection.execute(
                text(
                    "SELECT id, session_id, buyer, products, conditions, "
                    "delivery_start_date, delivery_end_date, cancelled "
                    "FROM orders ORDER BY id"
                )
            )
            assert isinstance(revision, str)
            return tables, revision, [dict(row) for row in result.mappings()]
    finally:
        await engine.dispose()


async def seed_legacy_orders(
    url: str,
    active_id: UUID,
    cancelled_id: UUID,
    product_id: UUID,
) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO products (id, name) VALUES (:id, :name)"),
                {"id": product_id, "name": "Tomate de teste da migration"},
            )
            statement = text(
                "INSERT INTO orders "
                "(id, session_id, buyer, products, conditions, "
                "delivery_start_date, delivery_end_date, cancelled) "
                "VALUES (:id, NULL, :buyer, :products, :conditions, "
                "DATE '2026-12-05', "
                "CASE WHEN :cancelled THEN DATE '2026-12-07' ELSE NULL END, "
                ":cancelled)"
            )
            await connection.execute(
                statement,
                [
                    {
                        "id": active_id,
                        "buyer": "Comprador antigo ativo",
                        "products": "  Tomate: 10 kg; Alface: 5 unidades\n",
                        "conditions": "Entregar pela manhã. Preservar este texto.",
                        "cancelled": False,
                    },
                    {
                        "id": cancelled_id,
                        "buyer": "Comprador antigo cancelado",
                        "products": "Mel: 2 potes",
                        "conditions": "Pedido já cancelado antes da migration.",
                        "cancelled": True,
                    },
                ],
            )
    finally:
        await engine.dispose()


async def check_items_table(url: str, order_id: UUID, product_id: UUID) -> None:
    engine = create_async_engine(url)
    item_id = uuid4()
    try:
        async with engine.begin() as connection:
            # A migration must not invent structured items for legacy free text.
            count = await connection.scalar(text("SELECT count(*) FROM order_items"))
            assert count == 0
            await connection.execute(
                text(
                    "INSERT INTO order_items "
                    "(id, order_id, product_id, quantity, unit) "
                    "VALUES (:id, :order_id, :product_id, 10.125, 'kg')"
                ),
                {"id": item_id, "order_id": order_id, "product_id": product_id},
            )
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT id, order_id, product_id, unit FROM order_items WHERE id = :id"
                ),
                {"id": item_id},
            )
            saved = result.mappings().one()
            assert saved["order_id"] == order_id
            assert saved["product_id"] == product_id
            assert saved["unit"] == "kg"
    finally:
        await engine.dispose()


def test_order_items_migration_preserves_legacy_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision(ITEM_REVISION)
    assert revision is not None
    parent = revision.down_revision
    assert isinstance(parent, str)

    # Separate container: never run downgrade against the developer's .env database.
    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_order_item_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        active_id, cancelled_id, product_id = uuid4(), uuid4(), uuid4()

        command.upgrade(config, parent)
        asyncio.run(seed_legacy_orders(url, active_id, cancelled_id, product_id))
        baseline_tables, current, original_orders = asyncio.run(snapshot(url))
        assert current == parent
        assert "order_items" not in baseline_tables
        assert len(original_orders) == 2

        command.upgrade(config, ITEM_REVISION)
        tables, current, orders = asyncio.run(snapshot(url))
        assert current == ITEM_REVISION
        assert tables == baseline_tables | {"order_items"}
        assert orders == original_orders
        asyncio.run(check_items_table(url, active_id, product_id))

        command.downgrade(config, parent)
        tables, current, orders = asyncio.run(snapshot(url))
        assert current == parent
        assert tables == baseline_tables
        assert orders == original_orders

        command.upgrade(config, ITEM_REVISION)
        tables, current, orders = asyncio.run(snapshot(url))
        assert current == ITEM_REVISION
        assert tables == baseline_tables | {"order_items"}
        assert orders == original_orders
        asyncio.run(check_items_table(url, active_id, product_id))
