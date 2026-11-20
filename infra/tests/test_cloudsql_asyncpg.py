import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

import cloudsql
import common
import provision
from common import InfraError


PROJECT_ID = "test-sabor-da-terra"
REGION = "us-central1"
INSTANCE_NAME = "sabor-da-terra-db"
DATABASE_NAME = "sabor_da_terra"
ADMIN_USER = "postgres"
MIGRATOR_USER = "sabor_da_terra_migrator"
APPLICATION_USER = "sabor_da_terra_app"

CONNECTION_NAME = (
    f"{PROJECT_ID}:{REGION}:{INSTANCE_NAME}"
)


@pytest.fixture(autouse=True)
def clear_secrets():
    common.clear_registered_secrets()

    yield

    common.clear_registered_secrets()


@pytest.fixture
def config():
    return {
        "project_id": PROJECT_ID,
        "region": REGION,
        "database": {
            "instance_name": INSTANCE_NAME,
            "database_name": DATABASE_NAME,
            "tier": "db-f1-micro",
            "storage_size_gb": 10,
            "backup_enabled": False,
            "deletion_protection": True,
            "admin_user": ADMIN_USER,
            "migrator_user": MIGRATOR_USER,
            "application_user": APPLICATION_USER,
        },
    }


@pytest.fixture
def instance():
    return {
        "name": INSTANCE_NAME,
        "databaseVersion": "POSTGRES_16",
        "region": REGION,
        "state": "RUNNABLE",
        "settings": {
            "edition": "ENTERPRISE",
            "tier": "db-f1-micro",
            "availabilityType": "ZONAL",
            "dataDiskType": "PD_SSD",
            "dataDiskSizeGb": "10",
            "storageAutoResize": False,
            "deletionProtectionEnabled": True,
            "connectorEnforcement": "REQUIRED",
            "backupConfiguration": {
                "enabled": False,
                "pointInTimeRecoveryEnabled": False,
            },
            "ipConfiguration": {
                "ipv4Enabled": True,
                "authorizedNetworks": [],
                "serverCaMode": "GOOGLE_MANAGED_INTERNAL_CA",
            },
        },
    }


def test_connection_name():
    assert cloudsql.connection_name(
        PROJECT_ID,
        REGION,
        INSTANCE_NAME,
    ) == CONNECTION_NAME


def test_validate_sql_instance_accepts_expected_config(
    config,
    instance,
):
    provision.validate_sql_instance(
        instance,
        config,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("databaseVersion", "POSTGRES_17"),
        ("region", "us-east1"),
    ],
)
def test_validate_sql_instance_rejects_wrong_metadata(
    config,
    instance,
    field,
    value,
):
    instance[field] = value

    with pytest.raises(InfraError):
        provision.validate_sql_instance(
            instance,
            config,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("edition", "ENTERPRISE_PLUS"),
        ("tier", "db-custom-2-7680"),
        ("availabilityType", "REGIONAL"),
        ("dataDiskType", "PD_HDD"),
        ("dataDiskSizeGb", "20"),
        ("storageAutoResize", True),
        ("deletionProtectionEnabled", False),
        ("connectorEnforcement", "NOT_REQUIRED"),
    ],
)
def test_validate_sql_instance_rejects_wrong_settings(
    config,
    instance,
    field,
    value,
):
    instance["settings"][field] = value

    with pytest.raises(
        InfraError,
        match="does not match",
    ):
        provision.validate_sql_instance(
            instance,
            config,
        )


@pytest.mark.parametrize(
    "field",
    [
        "enabled",
        "pointInTimeRecoveryEnabled",
    ],
)
def test_validate_sql_instance_rejects_backups(
    config,
    instance,
    field,
):
    instance["settings"]["backupConfiguration"][field] = True

    with pytest.raises(InfraError):
        provision.validate_sql_instance(
            instance,
            config,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ipv4Enabled", False),
        (
            "authorizedNetworks",
            [{"value": "0.0.0.0/0"}],
        ),
        (
            "serverCaMode",
            "GOOGLE_MANAGED_CAS_CA",
        ),
    ],
)
def test_validate_sql_instance_rejects_insecure_network(
    config,
    instance,
    field,
    value,
):
    instance["settings"]["ipConfiguration"][field] = value

    with pytest.raises(InfraError):
        provision.validate_sql_instance(
            instance,
            config,
        )


def test_ensure_sql_instance_reuses_existing(
    monkeypatch,
    config,
    instance,
):
    monkeypatch.setattr(
        provision,
        "get_sql_instance",
        Mock(return_value=instance),
    )

    run_command = Mock()
    confirm = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    monkeypatch.setattr(
        provision,
        "confirm",
        confirm,
    )

    result = provision.ensure_sql_instance(
        PROJECT_ID,
        config,
        "admin-password",
    )

    assert result == instance

    run_command.assert_not_called()
    confirm.assert_not_called()


def test_ensure_sql_instance_creates_expected_instance(
    monkeypatch,
    config,
    instance,
):
    monkeypatch.setattr(
        provision,
        "get_sql_instance",
        Mock(
            side_effect=[
                None,
                instance,
            ]
        ),
    )

    confirm = Mock()
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "confirm",
        confirm,
    )

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    password = "private-admin-password"

    result = provision.ensure_sql_instance(
        PROJECT_ID,
        config,
        password,
    )

    assert result == instance

    confirm.assert_called_once()

    command = run_command.call_args.args[0]

    expected = [
        "--database-version=POSTGRES_16",
        "--edition=enterprise",
        "--tier=db-f1-micro",
        "--availability-type=zonal",
        "--storage-size=10GB",
        "--storage-type=SSD",
        "--no-storage-auto-increase",
        "--no-backup",
        "--assign-ip",
        "--connector-enforcement=REQUIRED",
        "--server-ca-mode=GOOGLE_MANAGED_INTERNAL_CA",
        "--deletion-protection",
    ]

    for argument in expected:
        assert argument in command

    assert PROJECT_ID in command

    assert (
        password
        in run_command.call_args.kwargs["secrets"]
    )

    assert (
        run_command.call_args.kwargs["capture_output"]
        is True
    )


def test_ensure_sql_instance_does_not_modify_incompatible_instance(
    monkeypatch,
    config,
    instance,
):
    instance["settings"]["tier"] = (
        "db-custom-2-7680"
    )

    monkeypatch.setattr(
        provision,
        "get_sql_instance",
        Mock(return_value=instance),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    with pytest.raises(
        InfraError,
        match="does not match",
    ):
        provision.ensure_sql_instance(
            PROJECT_ID,
            config,
            "admin-password",
        )

    run_command.assert_not_called()


def test_ensure_sql_database_preserves_existing(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "describe_json",
        Mock(
            return_value={
                "name": DATABASE_NAME,
            }
        ),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.ensure_sql_database(
        PROJECT_ID,
        INSTANCE_NAME,
        DATABASE_NAME,
    )

    run_command.assert_not_called()


def test_ensure_sql_database_creates_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "describe_json",
        Mock(return_value=None),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.ensure_sql_database(
        PROJECT_ID,
        INSTANCE_NAME,
        DATABASE_NAME,
    )

    command = run_command.call_args.args[0]

    assert command[:4] == [
        "gcloud",
        "sql",
        "databases",
        "create",
    ]

    assert DATABASE_NAME in command
    assert INSTANCE_NAME in command
    assert PROJECT_ID in command


def test_build_database_url():
    result = provision.build_database_url(
        PROJECT_ID,
        REGION,
        INSTANCE_NAME,
        DATABASE_NAME,
        APPLICATION_USER,
        "private-password",
    )

    assert result == (
        f"postgresql+asyncpg://"
        f"{APPLICATION_USER}:private-password@/"
        f"{DATABASE_NAME}?host=/cloudsql/"
        f"{CONNECTION_NAME}"
    )


def test_database_url_encodes_special_characters():
    password = "password@:/?#%"

    url = provision.build_database_url(
        PROJECT_ID,
        REGION,
        INSTANCE_NAME,
        DATABASE_NAME,
        APPLICATION_USER,
        password,
    )

    username, recovered_password = (
        provision.get_database_url_credentials(
            url
        )
    )

    assert username == APPLICATION_USER
    assert recovered_password == password
    assert password not in url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "postgresql://localhost/db",
        "postgresql://user@localhost/db",
    ],
)
def test_database_url_credentials_rejects_invalid_url(
    url,
):
    with pytest.raises(InfraError):
        provision.get_database_url_credentials(
            url
        )


def test_database_url_is_registered_as_secret():
    url = provision.build_database_url(
        PROJECT_ID,
        REGION,
        INSTANCE_NAME,
        DATABASE_NAME,
        APPLICATION_USER,
        "private-password",
    )

    result = common.redact_text(url)

    assert "private-password" not in result
    assert url not in result


def test_quote_sql_literal():
    assert (
        provision.quote_sql_literal("a'b")
        == "'a''b'"
    )


def test_quote_sql_literal_rejects_null_character():
    with pytest.raises(InfraError):
        provision.quote_sql_literal(
            "invalid\x00value"
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "invalid-name",
        "invalid;DROP TABLE",
        "Uppercase",
        "1invalid",
        "a" * 64,
    ],
)
def test_quote_sql_identifier_rejects_invalid_values(
    value,
):
    with pytest.raises(InfraError):
        provision.quote_sql_identifier(
            value
        )


def test_quote_sql_identifier():
    assert (
        provision.quote_sql_identifier(
            APPLICATION_USER
        )
        == f'"{APPLICATION_USER}"'
    )


def test_database_setup_sql_creates_restricted_roles():
    sql = provision.build_database_setup_sql(
        database_name=DATABASE_NAME,
        admin_user=ADMIN_USER,
        migrator_user=MIGRATOR_USER,
        migrator_password="migrator-password",
        application_user=APPLICATION_USER,
        application_password="app-password",
    )

    assert f'CREATE ROLE "{MIGRATOR_USER}"' in sql

    assert f'CREATE ROLE "{APPLICATION_USER}"' in sql

    assert "NOSUPERUSER" in sql
    assert "NOCREATEDB" in sql
    assert "NOCREATEROLE" in sql

    assert "rolreplication" in sql
    assert "rolbypassrls" in sql
    assert "pg_auth_members" in sql

    assert (
        "CREATE EXTENSION IF NOT EXISTS vector"
        in sql
    )

    assert (
        f'GRANT "{MIGRATOR_USER}" '
        f'TO "{ADMIN_USER}" WITH INHERIT TRUE'
        in sql
    )

    assert (
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC"
        in sql
    )

    assert (
        f'REVOKE CREATE ON SCHEMA public '
        f'FROM "{APPLICATION_USER}"'
        in sql
    )

    assert (
        f'GRANT CREATE ON SCHEMA public\n'
        f'    TO "{MIGRATOR_USER}"'
        in sql
    )

    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE"
        in sql
    )

    assert (
        f'ALTER DEFAULT PRIVILEGES '
        f'FOR ROLE "{MIGRATOR_USER}"'
        in sql
    )


def test_database_setup_sql_escapes_passwords():
    sql = provision.build_database_setup_sql(
        DATABASE_NAME,
        ADMIN_USER,
        MIGRATOR_USER,
        "migration'password",
        APPLICATION_USER,
        "app'password",
    )

    assert "migration''password" in sql
    assert "app''password" in sql

    assert (
        "SET LOCAL standard_conforming_strings = on"
        in sql
    )


def test_database_setup_sql_rejects_duplicate_roles():
    with pytest.raises(
        InfraError,
        match="must be different",
    ):
        provision.build_database_setup_sql(
            DATABASE_NAME,
            ADMIN_USER,
            MIGRATOR_USER,
            "migrator-password",
            MIGRATOR_USER,
            "application-password",
        )


def test_proxy_command_uses_loopback_and_quota_project(
    monkeypatch,
):
    monkeypatch.setattr(
        cloudsql.shutil,
        "which",
        lambda name: name,
    )

    proxy = cloudsql.CloudSqlProxy(
        PROJECT_ID,
        CONNECTION_NAME,
        port=15432,
    )

    proxy.port = 15432

    command = proxy._command()

    assert "--address=127.0.0.1" in command
    assert "--port=15432" in command
    assert f"--quota-project={PROJECT_ID}" in command
    assert CONNECTION_NAME in command


def test_proxy_command_requires_port():
    proxy = cloudsql.CloudSqlProxy(
        PROJECT_ID,
        CONNECTION_NAME,
    )

    with pytest.raises(
        InfraError,
        match="port is not configured",
    ):
        proxy._command()


def test_find_free_tcp_port():
    port = cloudsql.find_free_tcp_port()

    assert 1 <= port <= 65535


def test_proxy_start_and_stop(monkeypatch):
    monkeypatch.setattr(
        cloudsql,
        "require_commands",
        Mock(),
    )

    monkeypatch.setattr(
        cloudsql,
        "find_free_tcp_port",
        Mock(return_value=15432),
    )

    process = Mock()
    process.poll.return_value = None

    popen = Mock(return_value=process)

    monkeypatch.setattr(
        cloudsql.subprocess,
        "Popen",
        popen,
    )

    proxy = cloudsql.CloudSqlProxy(
        PROJECT_ID,
        CONNECTION_NAME,
    )

    monkeypatch.setattr(
        proxy,
        "_wait_until_ready",
        Mock(),
    )

    with proxy as active_proxy:
        assert active_proxy.host == "127.0.0.1"
        assert active_proxy.port == 15432
        assert active_proxy._process is process

    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=10)

    assert proxy._process is None
    assert proxy._stderr is None


def test_proxy_kills_process_if_termination_times_out():
    proxy = cloudsql.CloudSqlProxy(
        PROJECT_ID,
        CONNECTION_NAME,
    )

    process = Mock()

    process.poll.return_value = None

    process.wait.side_effect = [
        subprocess.TimeoutExpired(
            cmd="cloud-sql-proxy",
            timeout=10,
        ),
        0,
    ]

    proxy._process = process

    proxy.stop()

    process.terminate.assert_called_once()
    process.kill.assert_called_once()

    assert proxy._process is None


def test_proxy_start_cleans_up_on_failure(monkeypatch):
    monkeypatch.setattr(
        cloudsql,
        "require_commands",
        Mock(),
    )

    monkeypatch.setattr(
        cloudsql,
        "find_free_tcp_port",
        Mock(return_value=15432),
    )

    process = Mock()
    process.poll.return_value = None

    monkeypatch.setattr(
        cloudsql.subprocess,
        "Popen",
        Mock(return_value=process),
    )

    proxy = cloudsql.CloudSqlProxy(
        PROJECT_ID,
        CONNECTION_NAME,
    )

    monkeypatch.setattr(
        proxy,
        "_wait_until_ready",
        Mock(
            side_effect=InfraError(
                "Proxy startup failed."
            )
        ),
    )

    with pytest.raises(
        InfraError,
        match="Proxy startup failed",
    ):
        proxy.start()

    process.terminate.assert_called_once()

    assert proxy._process is None
    assert proxy._stderr is None


def mock_postgres_connection():
    transaction = Mock()

    transaction.__aenter__ = AsyncMock(
        return_value=None
    )

    transaction.__aexit__ = AsyncMock(
        return_value=False
    )

    connection = Mock()

    connection.transaction.return_value = (
        transaction
    )

    connection.execute = AsyncMock()
    connection.close = AsyncMock()

    return connection, transaction


@pytest.mark.asyncio
async def test_run_postgres_sql_uses_transaction(
    monkeypatch,
):
    connection, transaction = (
        mock_postgres_connection()
    )

    connect = AsyncMock(
        return_value=connection
    )

    monkeypatch.setattr(
        cloudsql.asyncpg,
        "connect",
        connect,
    )

    await cloudsql.run_postgres_sql(
        host="127.0.0.1",
        port=15432,
        user=ADMIN_USER,
        password="private-password",
        database=DATABASE_NAME,
        sql="SELECT 1;",
    )

    kwargs = connect.call_args.kwargs

    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 15432
    assert kwargs["ssl"] is False
    assert kwargs["database"] == DATABASE_NAME
    assert kwargs["user"] == ADMIN_USER

    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()

    connection.execute.assert_awaited_once_with(
        "SELECT 1;"
    )

    connection.close.assert_awaited_once_with(
        timeout=10
    )


@pytest.mark.asyncio
async def test_run_postgres_sql_rejects_remote_host(
    monkeypatch,
):
    connect = AsyncMock()

    monkeypatch.setattr(
        cloudsql.asyncpg,
        "connect",
        connect,
    )

    with pytest.raises(
        InfraError,
        match="local Cloud SQL Auth Proxy",
    ):
        await cloudsql.run_postgres_sql(
            host="192.0.2.1",
            port=5432,
            user=ADMIN_USER,
            password="private-password",
            database=DATABASE_NAME,
            sql="SELECT 1;",
        )

    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_postgres_sql_sanitizes_connection_failure(
    monkeypatch,
):
    password = "private-password"

    monkeypatch.setattr(
        cloudsql.asyncpg,
        "connect",
        AsyncMock(
            side_effect=OSError(
                f"Connection failed: {password}"
            )
        ),
    )

    with pytest.raises(
        InfraError
    ) as error:
        await cloudsql.run_postgres_sql(
            host="127.0.0.1",
            port=15432,
            user=ADMIN_USER,
            password=password,
            database=DATABASE_NAME,
            sql="SELECT 1;",
        )

    assert password not in str(error.value)
    assert "[REDACTED]" in str(error.value)


@pytest.mark.asyncio
async def test_run_postgres_sql_closes_connection_on_failure(
    monkeypatch,
):
    connection, transaction = (
        mock_postgres_connection()
    )

    connection.execute.side_effect = (
        cloudsql.asyncpg.PostgresError(
            "SQL execution failed."
        )
    )

    monkeypatch.setattr(
        cloudsql.asyncpg,
        "connect",
        AsyncMock(
            return_value=connection
        ),
    )

    with pytest.raises(
        InfraError,
        match="Cloud SQL configuration failed",
    ):
        await cloudsql.run_postgres_sql(
            host="127.0.0.1",
            port=15432,
            user=ADMIN_USER,
            password="private-password",
            database=DATABASE_NAME,
            sql="INVALID SQL;",
        )

    transaction.__aexit__.assert_awaited_once()

    connection.close.assert_awaited_once_with(
        timeout=10
    )


def test_run_sql_with_proxy(monkeypatch):
    proxy = Mock()

    proxy.host = "127.0.0.1"
    proxy.port = 15432

    context = Mock()

    context.__enter__ = Mock(
        return_value=proxy
    )

    context.__exit__ = Mock(
        return_value=False
    )

    proxy_class = Mock(
        return_value=context
    )

    monkeypatch.setattr(
        cloudsql,
        "CloudSqlProxy",
        proxy_class,
    )

    run_postgres_sql = AsyncMock()

    monkeypatch.setattr(
        cloudsql,
        "run_postgres_sql",
        run_postgres_sql,
    )

    cloudsql.run_sql_with_proxy(
        PROJECT_ID,
        CONNECTION_NAME,
        DATABASE_NAME,
        ADMIN_USER,
        "private-password",
        "SELECT 1;",
    )

    proxy_class.assert_called_once_with(
        PROJECT_ID,
        CONNECTION_NAME,
        proxy_path="cloud-sql-proxy",
    )

    run_postgres_sql.assert_awaited_once_with(
        host="127.0.0.1",
        port=15432,
        user=ADMIN_USER,
        password="private-password",
        database=DATABASE_NAME,
        sql="SELECT 1;",
    )

    context.__exit__.assert_called_once()


@pytest.fixture
def stage6_operations(
    monkeypatch,
    instance,
):
    operations = Mock()

    for name in [
        "require_commands",
        "enable_apis",
        "get_sql_instance",
        "ensure_secret",
        "get_secret_value",
        "ensure_sql_instance",
        "ensure_sql_database",
        "get_secret",
        "get_enabled_secret_versions",
        "run_sql_with_proxy",
        "bind_secret_accessor",
    ]:
        monkeypatch.setattr(
            provision,
            name,
            getattr(operations, name),
        )

    operations.get_sql_instance.return_value = None

    operations.ensure_sql_instance.return_value = (
        instance
    )

    operations.get_secret.return_value = None

    operations.get_enabled_secret_versions.return_value = []

    operations.get_secret_value.side_effect = (
        lambda project_id, secret_name: {
            "database-admin-password": "admin-password",
            "database-migrator-password": "migrator-password",
        }[secret_name]
    )

    monkeypatch.setattr(
        provision.secrets,
        "token_urlsafe",
        Mock(
            return_value="generated-password"
        ),
    )

    return operations


def test_stage6_configures_database_and_scoped_secret(
    config,
    stage6_operations,
):
    operations = stage6_operations

    provision.configure_stage6(
        PROJECT_ID,
        config,
    )

    operations.ensure_sql_instance.assert_called_once_with(
        PROJECT_ID,
        config,
        "admin-password",
    )

    operations.ensure_sql_database.assert_called_once_with(
        PROJECT_ID,
        INSTANCE_NAME,
        DATABASE_NAME,
    )

    names = [
        call.args[1]
        for call in operations.ensure_secret.call_args_list
    ]

    assert "database-admin-password" in names
    assert "database-migrator-password" in names
    assert "database-url" in names

    operations.run_sql_with_proxy.assert_called_once()

    sql = (
        operations.run_sql_with_proxy
        .call_args.args[5]
    )

    assert (
        "CREATE EXTENSION IF NOT EXISTS vector"
        in sql
    )

    operations.bind_secret_accessor.assert_called_once_with(
        PROJECT_ID,
        "database-url",
        f"sabor-da-terra-api@{PROJECT_ID}.iam.gserviceaccount.com",
    )


def test_stage6_rejects_existing_instance_without_admin_secret(
    config,
    instance,
    stage6_operations,
):
    operations = stage6_operations

    operations.get_sql_instance.return_value = (
        instance
    )

    operations.get_enabled_secret_versions.return_value = []

    with pytest.raises(
        InfraError,
        match="administrator password secret",
    ):
        provision.configure_stage6(
            PROJECT_ID,
            config,
        )

    operations.ensure_secret.assert_not_called()
    operations.run_sql_with_proxy.assert_not_called()


def test_stage6_does_not_grant_access_if_sql_fails(
    config,
    stage6_operations,
):
    operations = stage6_operations

    operations.run_sql_with_proxy.side_effect = (
        InfraError("SQL configuration failed.")
    )

    with pytest.raises(
        InfraError,
        match="SQL configuration failed",
    ):
        provision.configure_stage6(
            PROJECT_ID,
            config,
        )

    operations.bind_secret_accessor.assert_not_called()


def test_stage6_rejects_incompatible_database_url(
    config,
    stage6_operations,
):
    operations = stage6_operations

    operations.get_secret.return_value = {
        "name": "database-url",
    }

    operations.get_enabled_secret_versions.return_value = [
        {
            "name": "projects/test/secrets/database-url/versions/1",
            "state": "ENABLED",
        },
    ]

    operations.get_secret_value.side_effect = [
        "admin-password",
        "migrator-password",
        "postgresql+asyncpg://other:password@localhost/other",
    ]

    with pytest.raises(
        InfraError,
        match="database-url does not match",
    ):
        provision.configure_stage6(
            PROJECT_ID,
            config,
        )

    operations.run_sql_with_proxy.assert_not_called()
    operations.bind_secret_accessor.assert_not_called()