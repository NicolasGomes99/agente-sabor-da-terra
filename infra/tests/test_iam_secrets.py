import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

import common
import provision
from common import InfraError


PROJECT_ID = "test-sabor-da-terra"

API_EMAIL = (
    f"sabor-da-terra-api@{PROJECT_ID}.iam.gserviceaccount.com"
)

TASKS_EMAIL = (
    f"sabor-da-terra-tasks@{PROJECT_ID}.iam.gserviceaccount.com"
)

SCHEDULER_EMAIL = (
    f"sabor-da-terra-scheduler@{PROJECT_ID}.iam.gserviceaccount.com"
)


@pytest.fixture(autouse=True)
def clear_secrets():
    common.clear_registered_secrets()

    yield

    common.clear_registered_secrets()


@pytest.fixture
def emails():
    return {
        "api": API_EMAIL,
        "tasks": TASKS_EMAIL,
        "scheduler": SCHEDULER_EMAIL,
    }


def completed(
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def secret_version(
    secret_name: str,
    version: int,
    state: str = "ENABLED",
) -> dict:
    return {
        "name": (
            f"projects/{PROJECT_ID}/secrets/"
            f"{secret_name}/versions/{version}"
        ),
        "state": state,
    }


def test_enable_stage_5_apis(monkeypatch):
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.enable_stage_5_apis(PROJECT_ID)

    command = run_command.call_args.args[0]

    assert "secretmanager.googleapis.com" in command
    assert "cloudtasks.googleapis.com" in command
    assert "cloudscheduler.googleapis.com" in command
    assert "iam.googleapis.com" in command
    assert PROJECT_ID in command


def test_get_service_account(monkeypatch):
    describe = Mock(
        return_value={
            "email": API_EMAIL,
        }
    )

    monkeypatch.setattr(
        provision,
        "describe_json",
        describe,
    )

    result = provision.get_service_account(
        PROJECT_ID,
        "sabor-da-terra-api",
    )

    assert result["email"] == API_EMAIL

    command = describe.call_args.args[0]

    assert API_EMAIL in command
    assert PROJECT_ID in command


def test_ensure_service_accounts_creates_missing(
    monkeypatch,
    emails,
):
    monkeypatch.setattr(
        provision,
        "get_service_account",
        Mock(return_value=None),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    assert (
        provision.ensure_service_accounts(PROJECT_ID)
        == emails
    )

    commands = [
        call.args[0]
        for call in run_command.call_args_list
    ]

    assert len(commands) == 3

    assert all(
        "create" in command
        for command in commands
    )

    assert all(
        "keys" not in command
        for command in commands
    )


def test_ensure_service_accounts_reuses_existing(
    monkeypatch,
    emails,
):
    monkeypatch.setattr(
        provision,
        "get_service_account",
        Mock(
            return_value={
                "disabled": False,
            }
        ),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    assert (
        provision.ensure_service_accounts(PROJECT_ID)
        == emails
    )

    run_command.assert_not_called()


def test_rejects_disabled_service_account(monkeypatch):
    monkeypatch.setattr(
        provision,
        "get_service_account",
        Mock(
            return_value={
                "disabled": True,
            }
        ),
    )

    with pytest.raises(
        InfraError,
        match="disabled",
    ):
        provision.ensure_service_accounts(
            PROJECT_ID
        )


def test_get_enabled_secret_versions(monkeypatch):
    versions = [
        secret_version("jwt-secret-key", 1),
        secret_version(
            "jwt-secret-key",
            2,
            "DISABLED",
        ),
        secret_version(
            "jwt-secret-key",
            3,
            "DESTROYED",
        ),
        secret_version("jwt-secret-key", 4),
    ]

    monkeypatch.setattr(
        provision,
        "describe_json",
        Mock(return_value=versions),
    )

    result = provision.get_enabled_secret_versions(
        PROJECT_ID,
        "jwt-secret-key",
    )

    assert result == [
        versions[0],
        versions[3],
    ]


def test_missing_secret_has_no_enabled_versions(monkeypatch):
    monkeypatch.setattr(
        provision,
        "describe_json",
        Mock(return_value=None),
    )

    assert provision.get_enabled_secret_versions(
        PROJECT_ID,
        "jwt-secret-key",
    ) == []


def test_get_secret_version_selects_highest_enabled(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(
            return_value=[
                secret_version("jwt-secret-key", 2),
                secret_version("jwt-secret-key", 10),
                secret_version("jwt-secret-key", 4),
            ]
        ),
    )

    assert provision.get_secret_version(
        PROJECT_ID,
        "jwt-secret-key",
    ) == "10"


def test_get_secret_version_rejects_missing_version(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(return_value=[]),
    )

    with pytest.raises(
        InfraError,
        match="no enabled version",
    ):
        provision.get_secret_version(
            PROJECT_ID,
            "jwt-secret-key",
        )


def test_get_secret_version_rejects_invalid_metadata(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(
            return_value=[
                {"name": "invalid-version"}
            ]
        ),
    )

    with pytest.raises(
        InfraError,
        match="Invalid version metadata",
    ):
        provision.get_secret_version(
            PROJECT_ID,
            "jwt-secret-key",
        )


def test_get_secret_value_uses_explicit_version(
    monkeypatch,
    capsys,
):
    value = "sensitive-secret-value"

    monkeypatch.setattr(
        provision,
        "get_secret_version",
        Mock(return_value="7"),
    )

    run_command = Mock(
        return_value=completed(
            stdout=f"{value}\n"
        )
    )

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    result = provision.get_secret_value(
        PROJECT_ID,
        "jwt-secret-key",
    )

    assert result == value

    command = run_command.call_args.args[0]

    assert command[:5] == [
        "gcloud",
        "secrets",
        "versions",
        "access",
        "7",
    ]

    assert "latest" not in command

    assert (
        run_command.call_args.kwargs["capture_output"]
        is True
    )

    assert value not in capsys.readouterr().out

    assert value not in common.redact_text(value)


def test_get_secret_value_rejects_empty_value(monkeypatch):
    monkeypatch.setattr(
        provision,
        "get_secret_version",
        Mock(return_value="1"),
    )

    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                stdout="\n"
            )
        ),
    )

    with pytest.raises(
        InfraError,
        match="empty",
    ):
        provision.get_secret_value(
            PROJECT_ID,
            "jwt-secret-key",
        )


def test_ensure_secret_preserves_existing(monkeypatch):
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(
            return_value={
                "name": "existing-secret",
            }
        ),
    )

    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(
            return_value=[
                secret_version("jwt-secret-key", 1)
            ]
        ),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    assert provision.ensure_secret(
        PROJECT_ID,
        "jwt-secret-key",
        "replacement-value",
    ) is False

    run_command.assert_not_called()


def test_ensure_secret_creates_secret_and_version(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(return_value=None),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    assert provision.ensure_secret(
        PROJECT_ID,
        "jwt-secret-key",
        "generated-secret",
    ) is True

    assert run_command.call_count == 2

    create_call, version_call = (
        run_command.call_args_list
    )

    assert create_call.args[0][:3] == [
        "gcloud",
        "secrets",
        "create",
    ]

    assert "automatic" in create_call.args[0]

    assert version_call.args[0][:4] == [
        "gcloud",
        "secrets",
        "versions",
        "add",
    ]

    assert "--data-file=-" in version_call.args[0]

    assert (
        version_call.kwargs["input_text"]
        == "generated-secret"
    )

    assert (
        "generated-secret"
        not in version_call.args[0]
    )


def test_ensure_secret_rejects_missing_initial_value(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(return_value=None),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    with pytest.raises(
        InfraError,
        match="requires an initial value",
    ):
        provision.ensure_secret(
            PROJECT_ID,
            "jwt-secret-key",
        )

    run_command.assert_not_called()


def test_ensure_secret_restores_missing_version(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(
            return_value={
                "name": "existing-secret",
            }
        ),
    )

    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(return_value=[]),
    )

    add_version = Mock()

    monkeypatch.setattr(
        provision,
        "add_secret_version",
        add_version,
    )

    assert provision.ensure_secret(
        PROJECT_ID,
        "jwt-secret-key",
        "restored-secret",
    ) is False

    add_version.assert_called_once_with(
        PROJECT_ID,
        "jwt-secret-key",
        "restored-secret",
    )


def test_ensure_secret_rejects_missing_enabled_version(
    monkeypatch,
):
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(
            return_value={
                "name": "existing-secret",
            }
        ),
    )

    monkeypatch.setattr(
        provision,
        "get_enabled_secret_versions",
        Mock(return_value=[]),
    )

    with pytest.raises(
        InfraError,
        match="no enabled version",
    ):
        provision.ensure_secret(
            PROJECT_ID,
            "jwt-secret-key",
        )


def test_add_secret_version_uses_stdin(monkeypatch):
    value = "private-api-key-value"

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.add_secret_version(
        PROJECT_ID,
        "gemini-api-key",
        value,
    )

    command = run_command.call_args.args[0]
    kwargs = run_command.call_args.kwargs

    assert "--data-file=-" in command
    assert value not in command
    assert kwargs["input_text"] == value
    assert kwargs["capture_output"] is True
    assert value in kwargs["secrets"]


def test_bind_project_role(monkeypatch):
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.bind_project_role(
        PROJECT_ID,
        API_EMAIL,
        "roles/cloudsql.client",
    )

    command = run_command.call_args.args[0]

    assert command[:3] == [
        "gcloud",
        "projects",
        "add-iam-policy-binding",
    ]

    assert PROJECT_ID in command
    assert f"serviceAccount:{API_EMAIL}" in command
    assert "roles/cloudsql.client" in command
    assert "--condition=None" in command


def test_bind_secret_accessor_is_resource_scoped(
    monkeypatch,
):
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.bind_secret_accessor(
        PROJECT_ID,
        "jwt-secret-key",
        API_EMAIL,
    )

    command = run_command.call_args.args[0]

    assert command[:3] == [
        "gcloud",
        "secrets",
        "add-iam-policy-binding",
    ]

    assert "jwt-secret-key" in command
    assert f"serviceAccount:{API_EMAIL}" in command
    assert "roles/secretmanager.secretAccessor" in command


def test_bind_service_account_user_is_resource_scoped(
    monkeypatch,
):
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.bind_service_account_user(
        PROJECT_ID,
        TASKS_EMAIL,
        API_EMAIL,
    )

    command = run_command.call_args.args[0]

    assert command[:4] == [
        "gcloud",
        "iam",
        "service-accounts",
        "add-iam-policy-binding",
    ]

    assert TASKS_EMAIL in command
    assert f"serviceAccount:{API_EMAIL}" in command
    assert "roles/iam.serviceAccountUser" in command


@pytest.fixture
def inference_operations(monkeypatch):
    operations = Mock()

    for name in [
        "enable_apis",
        "bind_project_role",
        "bind_secret_accessor",
        "ensure_secret",
        "get_secret",
        "get_enabled_secret_versions",
        "getpass",
    ]:
        monkeypatch.setattr(
            provision,
            name,
            getattr(operations, name),
        )

    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )

    return operations


def test_configure_vertex_inference(
    inference_operations,
):
    operations = inference_operations

    provision.configure_inference(
        PROJECT_ID,
        {
            "inference": {
                "mode": "vertex",
            },
        },
        API_EMAIL,
    )

    operations.enable_apis.assert_called_once_with(
        PROJECT_ID,
        ["aiplatform.googleapis.com"],
    )

    operations.bind_project_role.assert_called_once_with(
        PROJECT_ID,
        API_EMAIL,
        "roles/aiplatform.user",
    )

    operations.ensure_secret.assert_not_called()
    operations.bind_secret_accessor.assert_not_called()
    operations.getpass.assert_not_called()


def test_configure_developer_inference_uses_environment_key(
    monkeypatch,
    inference_operations,
):
    operations = inference_operations

    operations.get_secret.return_value = None

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "private-test-key",
    )

    provision.configure_inference(
        PROJECT_ID,
        {
            "inference": {
                "mode": "developer",
            },
        },
        API_EMAIL,
    )

    operations.enable_apis.assert_called_once_with(
        PROJECT_ID,
        ["generativelanguage.googleapis.com"],
    )

    operations.ensure_secret.assert_called_once_with(
        PROJECT_ID,
        "gemini-api-key",
        "private-test-key",
    )

    operations.bind_secret_accessor.assert_called_once_with(
        PROJECT_ID,
        "gemini-api-key",
        API_EMAIL,
    )

    operations.getpass.assert_not_called()
    operations.bind_project_role.assert_not_called()


def test_configure_developer_inference_preserves_secret(
    inference_operations,
):
    operations = inference_operations

    operations.get_secret.return_value = {
        "name": "existing-secret",
    }

    operations.get_enabled_secret_versions.return_value = [
        secret_version("gemini-api-key", 1),
    ]

    provision.configure_inference(
        PROJECT_ID,
        {"inference": {"mode": "developer"}},
        API_EMAIL,
    )

    operations.ensure_secret.assert_not_called()
    operations.getpass.assert_not_called()

    operations.bind_secret_accessor.assert_called_once_with(
        PROJECT_ID,
        "gemini-api-key",
        API_EMAIL,
    )


def test_configure_developer_inference_repairs_secret(
    inference_operations,
):
    operations = inference_operations

    operations.get_secret.return_value = {
        "name": "existing-secret",
    }

    operations.get_enabled_secret_versions.return_value = []

    operations.getpass.return_value = (
        "restored-private-key"
    )

    provision.configure_inference(
        PROJECT_ID,
        {"inference": {"mode": "developer"}},
        API_EMAIL,
    )

    operations.getpass.assert_called_once()

    operations.ensure_secret.assert_called_once_with(
        PROJECT_ID,
        "gemini-api-key",
        "restored-private-key",
    )


def test_configure_developer_requires_key(
    inference_operations,
):
    operations = inference_operations

    operations.get_secret.return_value = None
    operations.getpass.return_value = ""

    with pytest.raises(
        InfraError,
        match="GEMINI_API_KEY",
    ):
        provision.configure_inference(
            PROJECT_ID,
            {"inference": {"mode": "developer"}},
            API_EMAIL,
        )

    operations.ensure_secret.assert_not_called()
    operations.bind_secret_accessor.assert_not_called()


def test_configure_inference_rejects_unknown_mode(
    inference_operations,
):
    with pytest.raises(
        InfraError,
        match="Unsupported inference mode",
    ):
        provision.configure_inference(
            PROJECT_ID,
            {"inference": {"mode": "fallback"}},
            API_EMAIL,
        )

    inference_operations.enable_apis.assert_not_called()


def test_configure_stage_5_uses_least_privilege(
    monkeypatch,
    emails,
):
    operations = Mock()

    for name in [
        "enable_stage_5_apis",
        "ensure_service_accounts",
        "ensure_secret",
        "bind_project_role",
        "bind_secret_accessor",
        "bind_service_account_user",
        "configure_inference",
    ]:
        monkeypatch.setattr(
            provision,
            name,
            getattr(operations, name),
        )

    operations.ensure_service_accounts.return_value = (
        emails
    )

    monkeypatch.setattr(
        provision.secrets,
        "token_urlsafe",
        Mock(return_value="generated-jwt-key"),
    )

    config = {
        "inference": {
            "mode": "vertex",
        },
    }

    result = provision.configure_stage_5(
        PROJECT_ID,
        config,
    )

    assert result == emails

    operations.ensure_secret.assert_called_once_with(
        PROJECT_ID,
        "jwt-secret-key",
        "generated-jwt-key",
    )

    operations.bind_project_role.assert_called_once_with(
        PROJECT_ID,
        API_EMAIL,
        "roles/cloudsql.client",
    )

    operations.bind_service_account_user.assert_called_once_with(
        PROJECT_ID,
        TASKS_EMAIL,
        API_EMAIL,
    )

    operations.bind_secret_accessor.assert_called_once_with(
        PROJECT_ID,
        "jwt-secret-key",
        API_EMAIL,
    )

    operations.configure_inference.assert_called_once_with(
        PROJECT_ID,
        config,
        API_EMAIL,
    )

    secret_names = [
        call.args[1]
        for call in (
            operations.bind_secret_accessor.call_args_list
        )
    ]

    assert "database-url" not in secret_names
    assert "database-admin-password" not in secret_names
    assert "database-migrator-password" not in secret_names

    roles = [
        call.args[2]
        for call in (
            operations.bind_project_role.call_args_list
        )
    ]

    assert "roles/cloudtasks.enqueuer" not in roles
    assert "roles/editor" not in roles
    assert "roles/owner" not in roles
    assert "roles/secretmanager.secretAccessor" not in roles