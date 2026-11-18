import asyncio
from datetime import date
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

ORDER_REVISION = "cecd0d851e86"
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


async def _check_orders(url: str) -> None:
    engine = create_async_engine(url)
    insert_order = text(
        "INSERT INTO orders "
        "(id, buyer, products, conditions, delivery_start_date, delivery_end_date) "
        "VALUES (:id, 'Migration test', 'Tomato: 10 kg', '', "
        "DATE '2026-12-05', :end_date) "
        "RETURNING session_id, cancelled"
    )
    try:
        async with engine.connect() as connection:

            def read_schema(conn):
                inspector = inspect(conn)
                return (
                    inspector.get_columns("orders"),
                    inspector.get_pk_constraint("orders"),
                    inspector.get_foreign_keys("orders"),
                    inspector.get_unique_constraints("orders"),
                    inspector.get_check_constraints("orders"),
                )

            (
                columns,
                primary_key,
                foreign_keys,
                unique,
                checks,
            ) = await connection.run_sync(read_schema)
            by_name = {column["name"]: column for column in columns}
            assert set(by_name) == {
                "id",
                "session_id",
                "buyer",
                "products",
                "conditions",
                "delivery_start_date",
                "delivery_end_date",
                "cancelled",
            }
            assert by_name["session_id"]["nullable"] is True
            assert by_name["delivery_end_date"]["nullable"] is True
            for name in set(by_name) - {"session_id", "delivery_end_date"}:
                assert by_name[name]["nullable"] is False
            assert primary_key["constrained_columns"] == ["id"]
            assert any(
                fk["constrained_columns"] == ["session_id"]
                and fk["referred_table"] == "chat_sessions"
                and fk["referred_columns"] == ["id"]
                and fk["options"].get("ondelete") == "RESTRICT"
                for fk in foreign_keys
            )
            assert any(item["column_names"] == ["session_id"] for item in unique)
            assert any(item["name"] == "ck_orders_delivery_dates" for item in checks)

        # Commit real inserts: single date, equal dates and a date interval.
        async with engine.begin() as connection:
            for end_date in (None, date(2026, 12, 5), date(2026, 12, 7)):
                result = await connection.execute(
                    insert_order, {"id": uuid4(), "end_date": end_date}
                )
                row = result.one()
                assert row.session_id is None
                assert row.cancelled is False

        # Exercise the database constraint directly, without Pydantic.
        with pytest.raises(IntegrityError) as error:
            async with engine.begin() as connection:
                await connection.execute(
                    insert_order,
                    {"id": uuid4(), "end_date": date(2026, 12, 4)},
                )
        assert "ck_orders_delivery_dates" in str(error.value)

        async with engine.connect() as connection:
            count = await connection.scalar(text("SELECT count(*) FROM orders"))
            assert count == 3
    finally:
        await engine.dispose()


def test_order_migration_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision(ORDER_REVISION)
    assert revision is not None
    parent_revision = revision.down_revision
    assert isinstance(parent_revision, str)

    # Dedicated disposable database: never use DATABASE_URL from the local .env.
    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_order_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, parent_revision)
        baseline_tables, current = asyncio.run(_snapshot(url))
        assert current == parent_revision
        assert "orders" not in baseline_tables
        assert {"users", "documents", "chat_sessions"} <= baseline_tables

        command.upgrade(config, ORDER_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"orders"}
        assert current == ORDER_REVISION
        asyncio.run(_check_orders(url))

        command.downgrade(config, parent_revision)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables
        assert current == parent_revision

        command.upgrade(config, ORDER_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"orders"}
        assert current == ORDER_REVISION
        asyncio.run(_check_orders(url))
