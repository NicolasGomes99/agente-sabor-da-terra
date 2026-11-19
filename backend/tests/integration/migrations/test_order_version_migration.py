import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command

VERSION_REVISION = "d7a91f3c2b60"
BACKEND_DIR = Path(__file__).resolve().parents[3]


async def seed(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            order_id, product_id = uuid4(), uuid4()
            await connection.execute(text(
                "INSERT INTO orders (id, buyer, products, conditions, delivery_start_date, cancelled) "
                "VALUES (:id, 'Legado', '  Tomate: 2 kg  ', '', DATE '2026-12-05', false)"
            ), {"id": order_id})
            await connection.execute(text("INSERT INTO products (id, name) VALUES (:id, 'Tomate')"), {"id": product_id})
            await connection.execute(text(
                "INSERT INTO order_items (id, order_id, product_id, quantity, unit) "
                "VALUES (:id, :order_id, :product_id, 2.125, 'kg')"
            ), {"id": uuid4(), "order_id": order_id, "product_id": product_id})
            await connection.execute(text(
                "INSERT INTO orders (id, buyer, products, conditions, delivery_start_date, cancelled) "
                "VALUES (:id, 'Cancelado', '  Alface: 5 un  ', '', DATE '2026-12-05', true)"
            ), {"id": uuid4()})
    finally:
        await engine.dispose()


async def snapshot(url: str) -> tuple[list[dict], list[dict], str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            orders = (await connection.execute(text("SELECT * FROM orders ORDER BY id"))).mappings().all()
            items = (await connection.execute(text("SELECT * FROM order_items ORDER BY id"))).mappings().all()
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            return [dict(row) for row in orders], [dict(row) for row in items], revision
    finally:
        await engine.dispose()


def test_order_version_migration_preserves_orders_and_items(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [VERSION_REVISION]
    parent = script.get_revision(VERSION_REVISION).down_revision
    assert isinstance(parent, str)
    with PostgresContainer(
        image="postgres:16-alpine", username="test", password="test", dbname="test_order_version",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        command.upgrade(config, parent)
        asyncio.run(seed(url))
        before_orders, before_items, _ = asyncio.run(snapshot(url))
        command.upgrade(config, VERSION_REVISION)
        orders, items, revision = asyncio.run(snapshot(url))
        assert revision == VERSION_REVISION
        assert orders == [{**order, "version": 1} for order in before_orders]
        assert items == before_items
        command.downgrade(config, parent)
        orders, items, revision = asyncio.run(snapshot(url))
        assert revision == parent
        assert orders == before_orders
        assert items == before_items
        command.upgrade(config, VERSION_REVISION)
        orders, items, revision = asyncio.run(snapshot(url))
        assert revision == VERSION_REVISION
        assert orders == [{**order, "version": 1} for order in before_orders]
        assert items == before_items
