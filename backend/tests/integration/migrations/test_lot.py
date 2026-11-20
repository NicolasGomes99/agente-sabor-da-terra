import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from alembic import command

LOT_REVISION = "0009_create_lots"
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


async def _check_lots(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda conn: inspect(conn).get_columns("lots")
            )
            foreign_keys = await connection.run_sync(
                lambda conn: inspect(conn).get_foreign_keys("lots")
            )
            checks = await connection.run_sync(
                lambda conn: inspect(conn).get_check_constraints("lots")
            )
            by_name = {column["name"]: column for column in columns}
            assert set(by_name) == {
                "id",
                "item_id",
                "producer_id",
                "quantity",
                "unit",
                "delivery_date",
                "availability_confirmed",
            }
            assert by_name["item_id"]["nullable"] is True
            assert by_name["unit"]["nullable"] is True
            assert by_name["availability_confirmed"]["nullable"] is True
            for name in ("id", "producer_id", "quantity", "delivery_date"):
                assert by_name[name]["nullable"] is False
            assert any(
                fk["constrained_columns"] == ["item_id"]
                and fk["referred_table"] == "order_items"
                and fk["options"].get("ondelete") == "RESTRICT"
                for fk in foreign_keys
            )
            assert any(
                fk["constrained_columns"] == ["producer_id"]
                and fk["referred_table"] == "producers"
                for fk in foreign_keys
            )
            assert any(item["name"] == "ck_lots_quantity_positive" for item in checks)
            assert any(item["name"] == "ck_lots_unit_not_blank" for item in checks)

        # Insert a producer and a historical lot with a NULL item link.
        code = uuid4().hex[:10]
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO producers (id, code, name, cpf, active) "
                    "VALUES (:id, :code, 'Ana Silva', :cpf, true)"
                ),
                {"id": uuid4(), "code": code, "cpf": uuid4().hex[:11]},
            )
            producer_id = (
                await connection.execute(text("SELECT id FROM producers LIMIT 1"))
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO lots "
                    "(id, item_id, producer_id, quantity, unit, delivery_date, "
                    "availability_confirmed) "
                    "VALUES (:id, NULL, :producer_id, 300, NULL, DATE '2026-09-08', NULL)"
                ),
                {"id": uuid4(), "producer_id": producer_id},
            )

        # A lot pointing to a non-existent item must be rejected.
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO lots "
                        "(id, item_id, producer_id, quantity, unit, delivery_date, "
                        "availability_confirmed) "
                        "VALUES (:id, :item_id, :producer_id, 10, 'kg', "
                        "DATE '2026-12-05', true)"
                    ),
                    {
                        "id": uuid4(),
                        "item_id": uuid4(),
                        "producer_id": producer_id,
                    },
                )

        async with engine.connect() as connection:
            count = await connection.scalar(text("SELECT count(*) FROM lots"))
            assert count == 1
    finally:
        await engine.dispose()


def test_lot_migration_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision(LOT_REVISION)
    assert revision is not None
    parent_revision = revision.down_revision
    assert isinstance(parent_revision, str)

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_lot_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, parent_revision)
        baseline_tables, current = asyncio.run(_snapshot(url))
        assert current == parent_revision
        assert "lots" not in baseline_tables

        command.upgrade(config, LOT_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"lots"}
        assert current == LOT_REVISION
        asyncio.run(_check_lots(url))

        command.downgrade(config, parent_revision)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables
        assert current == parent_revision

        command.upgrade(config, LOT_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"lots"}
        assert current == LOT_REVISION
        asyncio.run(_check_lots(url))
