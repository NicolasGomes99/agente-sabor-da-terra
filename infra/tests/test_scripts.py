import json
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import make_url

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

import common
import deploy
import destroy
import hosting
import migrate
import provision

from common import InfraError


PROJECT_ID = "test-sabor-da-terra"
PROJECT_NUMBER = "123456"
REGION = "us-central1"
BILLING_ACCOUNT = "ABCDEF-123456-ABCDEF"

SITE_ID = "test-sabor-da-terra-hosting"

COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64

API_URL = "https://sabor-da-terra-api.run.app"

ORIGINS = [
    f"https://{SITE_ID}.web.app",
    f"https://{SITE_ID}.firebaseapp.com",
]


@pytest.fixture(autouse=True)
def clear_secrets():
    common.clear_registered_secrets()
    yield
    common.clear_registered_secrets()


@pytest.fixture
def config():
    path = (
        Path(__file__).resolve().parents[1]
        / "config.example.json"
    )

    config = json.loads(
        path.read_text(encoding="utf-8")
    )

    config["project_id"] = PROJECT_ID
    config["billing_account_id"] = BILLING_ACCOUNT
    config["inference"]["mode"] = "developer"

    return config


@pytest.fixture
def site():
    return {
        "name": (
            f"projects/{PROJECT_ID}/sites/{SITE_ID}"
        ),
        "type": "DEFAULT_SITE",
        "defaultUrl": ORIGINS[0],
    }


def completed(
    stdout="",
    stderr="",
    returncode=0,
):
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# Firebase Hosting


def test_run_firebase_json(monkeypatch):
    run_command = Mock(
        return_value=completed(
            stdout=json.dumps(
                {
                    "status": "success",
                    "result": [],
                }
            )
        )
    )

    monkeypatch.setattr(
        hosting,
        "run_command",
        run_command,
    )

    assert hosting.run_firebase_json(
        ["projects:list"]
    ) == []

    command = run_command.call_args.args[0]

    assert command == [
        "firebase",
        "projects:list",
        "--non-interactive",
        "--json",
    ]


@pytest.mark.parametrize(
    "response",
    [
        "invalid JSON",
        "[]",
        '{"status": "error"}',
        '{"status": "success"}',
    ],
)
def test_firebase_rejects_invalid_response(
    monkeypatch,
    response,
):
    monkeypatch.setattr(
        hosting,
        "run_command",
        Mock(
            return_value=completed(
                stdout=response
            )
        ),
    )

    with pytest.raises(InfraError):
        hosting.run_firebase_json(
            ["projects:list"]
        )


def test_firebase_project_already_associated(
    monkeypatch,
):
    monkeypatch.setattr(
        hosting,
        "get_firebase_project",
        Mock(
            return_value={
                "projectId": PROJECT_ID,
            }
        ),
    )

    confirm = Mock()
    run_json = Mock()

    monkeypatch.setattr(
        hosting,
        "run_firebase_json",
        run_json,
    )

    hosting.ensure_firebase_project(
        PROJECT_ID,
        confirm=confirm,
    )

    confirm.assert_not_called()
    run_json.assert_not_called()


def test_firebase_associates_missing_project(
    monkeypatch,
):
    monkeypatch.setattr(
        hosting,
        "get_firebase_project",
        Mock(
            side_effect=[
                None,
                {"projectId": PROJECT_ID},
            ]
        ),
    )

    run_json = Mock()
    confirm = Mock()

    monkeypatch.setattr(
        hosting,
        "run_firebase_json",
        run_json,
    )

    hosting.ensure_firebase_project(
        PROJECT_ID,
        confirm=confirm,
    )

    confirm.assert_called_once()

    run_json.assert_called_once_with(
        [
            "projects:addfirebase",
            PROJECT_ID,
        ]
    )


def test_get_default_site_does_not_assume_project_id(
    monkeypatch,
    site,
):
    monkeypatch.setattr(
        hosting,
        "list_hosting_sites",
        Mock(
            return_value=[
                {
                    "name": (
                        f"projects/{PROJECT_ID}/sites/other"
                    ),
                    "type": "USER_SITE",
                },
                site,
            ]
        ),
    )

    result = hosting.get_default_hosting_site(
        PROJECT_ID
    )

    assert result == site
    assert hosting.get_hosting_site_id(result) == SITE_ID
    assert hosting.get_hosting_origins(result) == ORIGINS


def test_get_default_site_rejects_multiple_defaults(
    monkeypatch,
    site,
):
    monkeypatch.setattr(
        hosting,
        "list_hosting_sites",
        Mock(return_value=[site, site]),
    )

    with pytest.raises(
        InfraError,
        match="Multiple default",
    ):
        hosting.get_default_hosting_site(
            PROJECT_ID
        )


def test_get_default_site_returns_none_when_empty(
    monkeypatch,
):
    monkeypatch.setattr(
        hosting,
        "list_hosting_sites",
        Mock(return_value=[]),
    )

    assert (
        hosting.get_default_hosting_site(PROJECT_ID)
        is None
    )


def test_hosting_rejects_unexpected_default_url(site):
    site["defaultUrl"] = "https://example.com"

    with pytest.raises(
        InfraError,
        match="Unexpected Firebase Hosting default URL",
    ):
        hosting.get_hosting_origins(site)


def test_publish_hosting_uses_explicit_project(
    monkeypatch,
    site,
):
    monkeypatch.setattr(
        hosting,
        "require_commands",
        Mock(),
    )

    monkeypatch.setattr(
        hosting,
        "require_default_hosting_site",
        Mock(return_value=site),
    )

    run_command = Mock()

    monkeypatch.setattr(
        hosting,
        "run_command",
        run_command,
    )

    assert hosting.publish_hosting(
        PROJECT_ID
    ) == ORIGINS

    run_command.assert_called_once_with(
        [
            "firebase",
            "deploy",
            "--only",
            "hosting",
            "--project",
            PROJECT_ID,
            "--non-interactive",
        ]
    )


# Migrations


def test_build_migration_url():
    password = "private-password@:/?#%"

    url = migrate.build_migration_url(
        host="127.0.0.1",
        port=15432,
        database="sabor_da_terra",
        username="migrator",
        password=password,
    )

    parsed = make_url(url)

    assert parsed.drivername == "postgresql+asyncpg"
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 15432
    assert parsed.database == "sabor_da_terra"
    assert parsed.username == "migrator"
    assert parsed.password == password
    assert parsed.query["ssl"] == "disable"

    assert password not in url
    assert url not in common.redact_text(url)


def test_get_migration_head(monkeypatch):
    directory = Mock()

    directory.get_heads.return_value = [
        "abc123",
    ]

    monkeypatch.setattr(
        migrate.ScriptDirectory,
        "from_config",
        Mock(return_value=directory),
    )

    assert migrate.get_migration_head() == "abc123"


@pytest.mark.parametrize(
    "heads",
    [
        [],
        ["abc123", "def456"],
    ],
)
def test_migration_requires_exactly_one_head(
    monkeypatch,
    heads,
):
    directory = Mock()
    directory.get_heads.return_value = heads

    monkeypatch.setattr(
        migrate.ScriptDirectory,
        "from_config",
        Mock(return_value=directory),
    )

    with pytest.raises(
        InfraError,
        match="Exactly one Alembic head",
    ):
        migrate.get_migration_head()


def test_operation_lock_acquires_and_releases(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "operation.local.json"

    monkeypatch.setattr(
        migrate,
        "LOCK_PATH",
        path,
    )

    with migrate.operation_lock():
        assert path.exists()

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        assert isinstance(data["pid"], int)

    assert not path.exists()


def test_operation_lock_rejects_concurrent_operation(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "operation.local.json"

    monkeypatch.setattr(
        migrate,
        "LOCK_PATH",
        path,
    )

    with migrate.operation_lock():
        with pytest.raises(InfraError):
            with migrate.operation_lock():
                pytest.fail(
                    "Concurrent operation acquired the lock."
                )

        assert path.exists()

    assert not path.exists()


def test_operation_lock_releases_on_failure(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "operation.local.json"

    monkeypatch.setattr(
        migrate,
        "LOCK_PATH",
        path,
    )

    with pytest.raises(RuntimeError):
        with migrate.operation_lock():
            raise RuntimeError("Test failure.")

    assert not path.exists()


def test_migrate_uses_migrator_credentials(
    monkeypatch,
    config,
):
    operations = Mock()

    for name in [
        "require_commands",
        "require_git_clean",
        "get_migration_head",
        "get_secret_value",
        "run_command",
        "verify_database_revision",
    ]:
        monkeypatch.setattr(
            migrate,
            name,
            getattr(operations, name),
        )

    operations.get_migration_head.return_value = (
        "abc123"
    )

    operations.get_secret_value.return_value = (
        "migrator-password"
    )

    proxy = Mock()
    proxy.host = "127.0.0.1"
    proxy.port = 15432

    monkeypatch.setattr(
        migrate,
        "CloudSqlProxy",
        Mock(
            return_value=nullcontext(proxy)
        ),
    )

    migrate.migrate(
        config,
        acquire_lock=False,
    )

    operations.get_secret_value.assert_called_once_with(
        PROJECT_ID,
        "database-migrator-password",
    )

    call = operations.run_command.call_args

    assert call.args[0] == [
        "uv",
        "run",
        "--locked",
        "alembic",
        "upgrade",
        "head",
    ]

    url = call.kwargs["env"]["DATABASE_URL"]

    parsed = make_url(url)

    assert parsed.username == (
        config["database"]["migrator_user"]
    )

    operations.verify_database_revision.assert_called_once_with(
        url,
        "abc123",
    )


# Artifact Registry and Storage


def test_repository_name(config):
    assert (
        provision.get_repository_name(config)
        == "sabor-da-terra"
    )


def test_default_bucket_name(config):
    assert (
        provision.get_bucket_name(config)
        == f"{PROJECT_ID}-documents"
    )


@pytest.fixture
def bucket():
    return {
        "projectNumber": PROJECT_NUMBER,
        "location": "US-CENTRAL1",
        "storageClass": "STANDARD",
        "iamConfiguration": {
            "uniformBucketLevelAccess": {
                "enabled": True,
            },
            "publicAccessPrevention": "enforced",
        },
        "softDeletePolicy": {
            "retentionDurationSeconds": "0",
        },
        "versioning": {
            "enabled": False,
        },
    }


def test_validate_storage_bucket(bucket):
    provision.validate_storage_bucket(
        bucket,
        PROJECT_NUMBER,
        REGION,
    )


def test_storage_rejects_foreign_bucket(bucket):
    bucket["projectNumber"] = "999999"

    with pytest.raises(
        InfraError,
        match="project ownership",
    ):
        provision.validate_storage_bucket(
            bucket,
            PROJECT_NUMBER,
            REGION,
        )


def test_storage_rejects_soft_delete(bucket):
    bucket["softDeletePolicy"][
        "retentionDurationSeconds"
    ] = "604800"

    with pytest.raises(
        InfraError,
        match="soft delete",
    ):
        provision.validate_storage_bucket(
            bucket,
            PROJECT_NUMBER,
            REGION,
        )


def test_storage_rejects_public_access(bucket):
    bucket["iamConfiguration"][
        "publicAccessPrevention"
    ] = "inherited"

    with pytest.raises(
        InfraError,
        match="public access prevention",
    ):
        provision.validate_storage_bucket(
            bucket,
            PROJECT_NUMBER,
            REGION,
        )


def test_validate_artifact_repository():
    provision.validate_artifact_repository(
        {
            "format": "DOCKER",
            "mode": "STANDARD_REPOSITORY",
        }
    )


def test_rejects_incompatible_artifact_repository():
    with pytest.raises(InfraError):
        provision.validate_artifact_repository(
            {
                "format": "MAVEN",
                "mode": "STANDARD_REPOSITORY",
            }
        )


# Deployment


def test_get_image_name(config):
    assert deploy.get_image_name(config) == (
        f"{REGION}-docker.pkg.dev/"
        f"{PROJECT_ID}/sabor-da-terra/backend"
    )


def test_existing_image_is_never_overwritten(
    monkeypatch,
    config,
):
    monkeypatch.setattr(
        deploy,
        "get_image_digest",
        Mock(return_value=DIGEST),
    )

    run_command = Mock()

    monkeypatch.setattr(
        deploy,
        "run_command",
        run_command,
    )

    result = deploy.build_and_push_image(
        config,
        COMMIT,
    )

    assert result == (
        f"{deploy.get_image_name(config)}@{DIGEST}"
    )

    run_command.assert_not_called()


def test_build_environment_for_developer_api(config):
    variables = deploy.build_environment_variables(
        config,
        ORIGINS,
    )

    assert variables[
        "DOCUMENT_STORAGE_BACKEND"
    ] == "gcs"

    assert variables[
        "DOCUMENT_STORAGE_BUCKET"
    ] == f"{PROJECT_ID}-documents"

    assert variables[
        "CORS_ALLOWED_ORIGINS"
    ] == ",".join(ORIGINS)

    assert variables[
        "GOOGLE_GENAI_USE_VERTEXAI"
    ] == "FALSE"

    assert "GEMINI_API_KEY" not in variables
    assert "DATABASE_URL" not in variables
    assert "JWT_SECRET_KEY" not in variables


def test_build_environment_for_vertex(config):
    config["inference"]["mode"] = "vertex"

    variables = deploy.build_environment_variables(
        config,
        ORIGINS,
    )

    assert variables[
        "GOOGLE_GENAI_USE_VERTEXAI"
    ] == "TRUE"

    assert variables[
        "GOOGLE_CLOUD_PROJECT"
    ] == PROJECT_ID

    assert variables[
        "GOOGLE_CLOUD_LOCATION"
    ] == "global"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "developer",
            {
                "DATABASE_URL": "database-url:3",
                "JWT_SECRET_KEY": "jwt-secret-key:3",
                "GEMINI_API_KEY": "gemini-api-key:3",
            },
        ),
        (
            "vertex",
            {
                "DATABASE_URL": "database-url:3",
                "JWT_SECRET_KEY": "jwt-secret-key:3",
            },
        ),
    ],
)
def test_secret_references_use_explicit_versions(
    monkeypatch,
    config,
    mode,
    expected,
):
    config["inference"]["mode"] = mode

    monkeypatch.setattr(
        deploy,
        "get_secret_version",
        Mock(return_value="3"),
    )

    assert (
        deploy.build_secret_references(config)
        == expected
    )


def test_gcloud_mapping_preserves_cors_list():
    result = deploy.encode_gcloud_mapping(
        {
            "CORS_ALLOWED_ORIGINS": ",".join(ORIGINS),
            "OTHER": "value",
        }
    )

    assert result.startswith("^@^")
    assert ",".join(ORIGINS) in result
    assert "@OTHER=value" in result


def test_gcloud_mapping_rejects_delimiter_in_value():
    with pytest.raises(InfraError):
        deploy.encode_gcloud_mapping(
            {"VARIABLE": "invalid@value"}
        )


def test_cloud_run_command(config):
    image = (
        f"{deploy.get_image_name(config)}@{DIGEST}"
    )

    command = deploy.build_cloud_run_command(
        config,
        image,
        {"DOCUMENT_STORAGE_BACKEND": "gcs"},
        {
            "DATABASE_URL": "database-url:1",
            "JWT_SECRET_KEY": "jwt-secret-key:1",
        },
    )

    assert command[:3] == [
        "gcloud",
        "run",
        "deploy",
    ]

    expected = [
        "--execution-environment=gen1",
        "--ingress=all",
        "--no-invoker-iam-check",
        "--cpu=1",
        "--memory=512Mi",
        "--min=0",
        "--max=2",
        "--concurrency=10",
        "--timeout=300s",
        "--cpu-throttling",
        "--set-cloudsql-instances",
        "--set-env-vars",
        "--set-secrets",
    ]

    for argument in expected:
        assert argument in command

    assert image in command
    assert PROJECT_ID in command
    assert REGION in command

    assert (
        f"{PROJECT_ID}:{REGION}:sabor-da-terra-db"
        in command
    )

    assert (
        f"sabor-da-terra-api@{PROJECT_ID}"
        ".iam.gserviceaccount.com"
        in command
    )


def test_build_frontend_uses_backend_url(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        deploy,
        "FRONTEND_DIR",
        tmp_path,
    )

    dist = tmp_path / "dist"
    dist.mkdir()

    (dist / "index.html").write_text(
        "<html></html>",
        encoding="utf-8",
    )

    run_command = Mock()

    monkeypatch.setattr(
        deploy,
        "run_command",
        run_command,
    )

    deploy.build_frontend(API_URL)

    install, build = run_command.call_args_list

    assert install.args[0] == [
        "npm",
        "ci",
    ]

    assert build.args[0] == [
        "npm",
        "run",
        "build",
    ]

    assert build.kwargs["env"] == {
        "VITE_API_URL": API_URL,
    }


@pytest.fixture
def deploy_operations(
    monkeypatch,
    site,
):
    operations = Mock()

    names = [
        "require_commands",
        "require_git_clean",
        "get_git_commit",
        "get_migration_head",
        "get_active_account",
        "ensure_docker_available",
        "verify_provisioned_resources",
        "require_default_hosting_site",
        "build_secret_references",
        "get_secret_version",
        "confirm",
        "get_cloud_run_service",
        "build_and_push_image",
        "verify_git_commit",
        "migrate",
        "deploy_backend",
        "verify_backend_http",
        "build_frontend",
        "publish_hosting",
        "verify_frontend_http",
    ]

    for name in names:
        monkeypatch.setattr(
            deploy,
            name,
            getattr(operations, name),
        )

    monkeypatch.setattr(
        deploy,
        "operation_lock",
        nullcontext,
    )

    operations.get_git_commit.return_value = COMMIT
    operations.get_migration_head.return_value = "abc123"
    operations.get_active_account.return_value = "user@example.com"

    operations.require_default_hosting_site.return_value = (
        site
    )

    operations.get_cloud_run_service.return_value = None

    operations.deploy_backend.return_value = API_URL

    operations.publish_hosting.return_value = ORIGINS

    return operations


def test_deploy_respects_operation_order(
    config,
    deploy_operations,
):
    operations = deploy_operations

    deploy.deploy(config)

    call_names = [
        call[0]
        for call in operations.mock_calls
    ]

    expected = [
        "build_and_push_image",
        "migrate",
        "deploy_backend",
        "verify_backend_http",
        "build_frontend",
        "publish_hosting",
        "verify_frontend_http",
    ]

    indexes = [
        call_names.index(name)
        for name in expected
    ]

    assert indexes == sorted(indexes)

    operations.migrate.assert_called_once_with(
        config,
        acquire_lock=False,
    )


def test_deploy_stops_when_migration_fails(
    config,
    deploy_operations,
):
    operations = deploy_operations

    operations.migrate.side_effect = InfraError(
        "Migration failed."
    )

    with pytest.raises(
        InfraError,
        match="Migration failed",
    ):
        deploy.deploy(config)

    operations.deploy_backend.assert_not_called()
    operations.build_frontend.assert_not_called()
    operations.publish_hosting.assert_not_called()


def test_deploy_stops_when_backend_verification_fails(
    config,
    deploy_operations,
):
    operations = deploy_operations

    operations.verify_backend_http.side_effect = (
        InfraError("Backend verification failed.")
    )

    with pytest.raises(
        InfraError,
        match="Backend verification failed",
    ):
        deploy.deploy(config)

    operations.build_frontend.assert_not_called()
    operations.publish_hosting.assert_not_called()


# Destruction


def test_confirm_destruction_requires_exact_project_id(
    monkeypatch,
):
    monkeypatch.setattr(
        "builtins.input",
        lambda _: "another-project",
    )

    with pytest.raises(
        InfraError,
        match="confirmation failed",
    ):
        destroy.confirm_destruction(PROJECT_ID)


def test_confirm_destruction_accepts_exact_project_id(
    monkeypatch,
):
    monkeypatch.setattr(
        "builtins.input",
        lambda _: PROJECT_ID,
    )

    destroy.confirm_destruction(PROJECT_ID)


def test_get_budget_id():
    budget = {
        "name": (
            f"billingAccounts/{BILLING_ACCOUNT}"
            "/budgets/abc123"
        )
    }

    assert destroy.get_budget_id(
        budget,
        BILLING_ACCOUNT,
    ) == "abc123"


def test_get_budget_id_rejects_foreign_account():
    budget = {
        "name": (
            "billingAccounts/OTHER1-OTHER2-OTHER3"
            "/budgets/abc123"
        )
    }

    with pytest.raises(InfraError):
        destroy.get_budget_id(
            budget,
            BILLING_ACCOUNT,
        )


def test_destroy_rejects_different_billing_account(
    monkeypatch,
    config,
):
    monkeypatch.setattr(
        destroy,
        "get_project_billing",
        Mock(
            return_value={
                "billingAccountName": (
                    "billingAccounts/OTHER1-OTHER2-OTHER3"
                ),
            }
        ),
    )

    with pytest.raises(
        InfraError,
        match="different billing account",
    ):
        destroy.verify_billing_account(config)


def test_destroy_preserves_shared_budgets(
    monkeypatch,
    config,
):
    managed = {
        "displayName": (
            f"Sabor da Terra - {PROJECT_ID}"
        ),
        "budgetFilter": {
            "projects": [
                f"projects/{PROJECT_NUMBER}",
            ],
        },
    }

    shared = {
        "displayName": "Shared budget",
        "budgetFilter": {
            "projects": [
                f"projects/{PROJECT_NUMBER}",
                "projects/999999",
            ],
        },
    }

    monkeypatch.setattr(
        destroy,
        "run_json",
        Mock(
            return_value=[
                managed,
                shared,
            ]
        ),
    )

    assert destroy.get_project_budgets(
        config,
        PROJECT_NUMBER,
    ) == [managed]


def test_destroy_rejects_foreign_bucket(
    monkeypatch,
    config,
):
    monkeypatch.setattr(
        destroy,
        "get_storage_bucket",
        Mock(
            return_value={
                "projectNumber": "999999",
            }
        ),
    )

    run_command = Mock()

    monkeypatch.setattr(
        destroy,
        "run_command",
        run_command,
    )

    with pytest.raises(
        InfraError,
        match="ownership verification failed",
    ):
        destroy.delete_storage_bucket(
            config,
            PROJECT_NUMBER,
        )

    run_command.assert_not_called()


@pytest.fixture
def destroy_operations(monkeypatch):
    operations = Mock()

    names = [
        "require_commands",
        "get_active_account",
        "get_project",
        "verify_billing_account",
        "get_enabled_services",
        "inspect_resources",
        "print_destroy_plan",
        "confirm_destruction",
        "confirm_external_credentials_revoked",
        "pause_automatic_triggers",
        "delete_cloud_run",
        "delete_cloud_sql",
        "delete_storage_bucket",
        "delete_artifact_repository",
        "verify_residual_resources",
        "delete_project_budgets",
        "unlink_project_billing",
        "delete_project",
    ]

    for name in names:
        monkeypatch.setattr(
            destroy,
            name,
            getattr(operations, name),
        )

    monkeypatch.setattr(
        destroy,
        "operation_lock",
        nullcontext,
    )

    operations.get_active_account.return_value = (
        "user@example.com"
    )

    operations.get_project.return_value = {
        "lifecycleState": "ACTIVE",
        "projectNumber": PROJECT_NUMBER,
    }

    operations.get_enabled_services.return_value = {
        "run.googleapis.com",
        "sqladmin.googleapis.com",
        "storage.googleapis.com",
        "artifactregistry.googleapis.com",
    }

    operations.inspect_resources.return_value = {
        "cloud_run": {},
        "cloud_sql": {},
        "storage": {},
        "artifacts": {},
        "budgets": [],
    }

    return operations


def test_destroy_respects_safe_operation_order(
    config,
    destroy_operations,
):
    operations = destroy_operations

    destroy.destroy(config)

    call_names = [
        call[0]
        for call in operations.mock_calls
    ]

    expected = [
        "inspect_resources",
        "confirm_destruction",
        "confirm_external_credentials_revoked",
        "pause_automatic_triggers",
        "delete_cloud_run",
        "delete_cloud_sql",
        "delete_storage_bucket",
        "delete_artifact_repository",
        "verify_residual_resources",
        "delete_project_budgets",
        "unlink_project_billing",
        "delete_project",
    ]

    indexes = [
        call_names.index(name)
        for name in expected
    ]

    assert indexes == sorted(indexes)


def test_destroy_does_not_delete_without_confirmation(
    config,
    destroy_operations,
):
    operations = destroy_operations

    operations.confirm_destruction.side_effect = (
        InfraError("Destruction cancelled.")
    )

    with pytest.raises(
        InfraError,
        match="Destruction cancelled",
    ):
        destroy.destroy(config)

    operations.pause_automatic_triggers.assert_not_called()
    operations.delete_cloud_run.assert_not_called()
    operations.delete_cloud_sql.assert_not_called()
    operations.delete_storage_bucket.assert_not_called()
    operations.unlink_project_billing.assert_not_called()
    operations.delete_project.assert_not_called()


def test_destroy_stops_when_residual_resources_exist(
    config,
    destroy_operations,
):
    operations = destroy_operations

    operations.verify_residual_resources.side_effect = (
        InfraError("Residual resources found.")
    )

    with pytest.raises(
        InfraError,
        match="Residual resources found",
    ):
        destroy.destroy(config)

    operations.delete_project_budgets.assert_not_called()
    operations.unlink_project_billing.assert_not_called()
    operations.delete_project.assert_not_called()