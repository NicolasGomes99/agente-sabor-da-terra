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

LOT_IMPORT_REVISION = "0010_create_lot_imports"
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


async def _check_lot_imports(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            columns = await connection.run_sync(
                lambda conn: inspect(conn).get_columns("lot_imports")
            )
            foreign_keys = await connection.run_sync(
                lambda conn: inspect(conn).get_foreign_keys("lot_imports")
            )
            unique = await connection.run_sync(
                lambda conn: inspect(conn).get_unique_constraints("lot_imports")
            )
            by_name = {column["name"]: column for column in columns}
            assert set(by_name) == {
                "lot_id",
                "source_file",
                "record_id",
                "record_fields",
            }
            for name in ("lot_id", "source_file", "record_id", "record_fields"):
                assert by_name[name]["nullable"] is False
            assert any(
                fk["constrained_columns"] == ["lot_id"]
                and fk["referred_table"] == "lots"
                and fk["options"].get("ondelete") == "CASCADE"
                for fk in foreign_keys
            )
            assert any(
                item["column_names"] == ["source_file", "record_id"]
                for item in unique
            )

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO producers (id, code, name, cpf, active) "
                    "VALUES (:id, :code, 'Ana Silva', :cpf, true)"
                ),
                {"id": uuid4(), "code": uuid4().hex[:10], "cpf": uuid4().hex[:11]},
            )
            producer_id = (
                await connection.execute(text("SELECT id FROM producers LIMIT 1"))
            ).scalar_one()
            lot_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO lots "
                    "(id, item_id, producer_id, quantity, unit, delivery_date, "
                    "availability_confirmed) "
                    "VALUES (:id, NULL, :producer_id, 300, 'unidades', "
                    "DATE '2026-09-08', NULL)"
                ),
                {"id": lot_id, "producer_id": producer_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO lot_imports "
                    "(lot_id, source_file, record_id, record_fields) "
                    "VALUES (:lot_id, 'lotes.csv', 'LOT-2026-0094', "
                    "'{\"produto\": \"alface\"}'::json)"
                ),
                {"lot_id": lot_id},
            )

        # (source_file, record_id) deve ser único.
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO lot_imports "
                        "(lot_id, source_file, record_id, record_fields) "
                        "VALUES (:lot_id, 'lotes.csv', 'LOT-2026-0094', "
                        "'{}'::json)"
                    ),
                    {"lot_id": uuid4()},
                )
    finally:
        await engine.dispose()


def test_lot_import_migration_upgrade_downgrade_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    revision = ScriptDirectory.from_config(config).get_revision(
        LOT_IMPORT_REVISION
    )
    assert revision is not None
    parent_revision = revision.down_revision
    assert isinstance(parent_revision, str)

    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_lot_import_migration",
    ) as container:
        url = container.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)

        command.upgrade(config, parent_revision)
        baseline_tables, current = asyncio.run(_snapshot(url))
        assert current == parent_revision
        assert "lot_imports" not in baseline_tables

        command.upgrade(config, LOT_IMPORT_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"lot_imports"}
        assert current == LOT_IMPORT_REVISION
        asyncio.run(_check_lot_imports(url))

        command.downgrade(config, parent_revision)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables
        assert current == parent_revision

        command.upgrade(config, LOT_IMPORT_REVISION)
        tables, current = asyncio.run(_snapshot(url))
        assert tables == baseline_tables | {"lot_imports"}
        assert current == LOT_IMPORT_REVISION
        asyncio.run(_check_lot_imports(url))
