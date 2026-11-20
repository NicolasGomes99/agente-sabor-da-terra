import asyncio
import json
import os
from contextlib import contextmanager, nullcontext
from typing import Iterator

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, pool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from cloudsql import CloudSqlProxy, connection_name
from common import (
    REPOSITORY_ROOT,
    InfraError,
    base_parser,
    main_entry,
    redact_text,
    register_secret,
    require_commands,
    require_git_clean,
    run_command,
)
from provision import get_secret_value


BACKEND_DIR = REPOSITORY_ROOT / "backend"
ALEMBIC_CONFIG = BACKEND_DIR / "alembic.ini"
LOCK_PATH = REPOSITORY_ROOT / "infra" / "operation.local.json"


@contextmanager
def operation_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            LOCK_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        raise InfraError(
            "Another infrastructure operation is running, "
            f"or a stale lock exists at {LOCK_PATH}. "
            "Verify that no operation is running before removing it."
        ) from None
    except OSError as error:
        raise InfraError(
            f"Could not acquire infrastructure lock: {error}"
        ) from None

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid()}, stream)

        yield

    finally:
        LOCK_PATH.unlink(missing_ok=True)


def get_migration_head() -> str:
    config = Config(str(ALEMBIC_CONFIG))

    try:
        directory = ScriptDirectory.from_config(config)
        heads = directory.get_heads()
    except Exception as error:
        raise InfraError(
            f"Could not inspect Alembic revisions: "
            f"{redact_text(str(error))}"
        ) from None

    if len(heads) != 1:
        raise InfraError(
            "Exactly one Alembic head is required. "
            f"Found {len(heads)}: {', '.join(heads) or 'none'}."
        )

    return heads[0]


def build_migration_url(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> str:
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"ssl": "disable"},
    )

    value = url.render_as_string(hide_password=False)

    register_secret(password)
    register_secret(value)

    return value


async def get_database_heads(
    database_url: str,
) -> tuple[str, ...]:
    engine = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
        connect_args={
            "timeout": 15,
            "command_timeout": 60,
        },
    )

    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: (
                    MigrationContext.configure(
                        sync_connection
                    ).get_current_heads()
                )
            )

    except (SQLAlchemyError, OSError, TimeoutError) as error:
        raise InfraError(
            "Could not verify the database revision: "
            f"{redact_text(str(error))}"
        ) from None

    finally:
        await engine.dispose()


def verify_database_revision(
    database_url: str,
    expected_head: str,
) -> None:
    current_heads = asyncio.run(
        get_database_heads(database_url)
    )

    if set(current_heads) != {expected_head}:
        raise InfraError(
            f"Unexpected database revision. "
            f"Expected {expected_head}; "
            f"found {', '.join(current_heads) or 'none'}."
        )

    print(f"Database revision verified: {expected_head}")


def migrate(
    config: dict,
    *,
    acquire_lock: bool = True,
) -> None:
    project_id = config["project_id"]
    region = config["region"]
    database_config = config["database"]

    proxy_path = os.getenv(
        "CLOUD_SQL_PROXY_BIN",
        "cloud-sql-proxy",
    )

    require_commands([
        "gcloud",
        "uv",
        "git",
        proxy_path,
    ])

    lock = (
        operation_lock()
        if acquire_lock
        else nullcontext()
    )

    with lock:
        require_git_clean()

        expected_head = get_migration_head()

        print(f"Expected Alembic head: {expected_head}")

        password = get_secret_value(
            project_id,
            "database-migrator-password",
        )

        instance_connection = connection_name(
            project_id,
            region,
            database_config["instance_name"],
        )

        with CloudSqlProxy(
            project_id,
            instance_connection,
            proxy_path=proxy_path,
        ) as proxy:
            if proxy.port is None:
                raise InfraError(
                    "Cloud SQL Auth Proxy has no assigned port."
                )

            database_url = build_migration_url(
                host=proxy.host,
                port=proxy.port,
                database=database_config["database_name"],
                username=database_config["migrator_user"],
                password=password,
            )

            print("Applying Alembic migrations...")

            run_command(
                [
                    "uv",
                    "run",
                    "--locked",
                    "alembic",
                    "upgrade",
                    "head",
                ],
                cwd=BACKEND_DIR,
                env={
                    "DATABASE_URL": database_url,
                },
                capture_output=True,
                secrets=[
                    password,
                    database_url,
                ],
            )

            verify_database_revision(
                database_url,
                expected_head,
            )

        print("Database migrations completed successfully.")


if __name__ == "__main__":
    main_entry(
        base_parser(
            "Run the application database migrations"
        ),
        migrate,
    )