import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import provision
from common import InfraError


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_enable_stage_5_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    provision.enable_stage_5_apis("test-sabor-da-terra")

    command = run_command.call_args.args[0]
    assert "secretmanager.googleapis.com" in command
    assert "cloudtasks.googleapis.com" in command
    assert "cloudscheduler.googleapis.com" in command
    assert "iam.googleapis.com" in command


def test_get_service_account_returns_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                json.dumps({"email": "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com"})
            )
        ),
    )

    account = provision.get_service_account(
        "test-sabor-da-terra",
        "sabor-da-terra-api",
    )

    assert account["email"].endswith(".iam.gserviceaccount.com")


def test_get_service_account_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed(returncode=1)),
    )

    assert provision.get_service_account(
        "test-sabor-da-terra",
        "sabor-da-terra-api",
    ) is None


def test_ensure_service_accounts_creates_missing_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "get_service_account", Mock(return_value=None))
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    emails = provision.ensure_service_accounts("test-sabor-da-terra")

    assert set(emails) == {"api", "tasks", "scheduler"}
    commands = [call.args[0] for call in run_command.call_args_list]
    assert len(commands) == 3
    assert all("create" in command for command in commands)
    assert all("keys" not in command for command in commands)


def test_ensure_service_accounts_reuses_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "get_service_account",
        Mock(return_value={"email": "existing"}),
    )
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    emails = provision.ensure_service_accounts("test-sabor-da-terra")

    assert emails["api"].startswith("sabor-da-terra-api@")
    run_command.assert_not_called()


def test_get_secret_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed(json.dumps({"name": "projects/test/secrets/jwt-secret-key"}))),
    )

    secret = provision.get_secret("test-sabor-da-terra", "jwt-secret-key")

    assert secret["name"].endswith("/jwt-secret-key")


def test_get_secret_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed(returncode=1)),
    )

    assert provision.get_secret("test-sabor-da-terra", "jwt-secret-key") is None


def test_ensure_secret_preserves_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provision,
        "get_secret",
        Mock(return_value={"name": "existing"}),
    )
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    assert provision.ensure_secret(
        "test-sabor-da-terra",
        "jwt-secret-key",
        "must-not-be-written",
    ) is False
    run_command.assert_not_called()


def test_ensure_secret_creates_secret_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "get_secret", Mock(return_value=None))
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    assert provision.ensure_secret(
        "test-sabor-da-terra",
        "jwt-secret-key",
        "generated-secret",
    ) is True

    commands = [call.args[0] for call in run_command.call_args_list]
    assert any(command[:3] == ["gcloud", "secrets", "create"] for command in commands)
    assert any("automatic" in command for command in commands)
    assert any("versions" in command and "add" in command for command in commands)
    version_call = next(call for call in run_command.call_args_list if "versions" in call.args[0])
    assert version_call.kwargs["input_text"] == "generated-secret"


def test_bind_project_role(monkeypatch: pytest.MonkeyPatch) -> None:
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    provision.bind_project_role(
        "test-sabor-da-terra",
        "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com",
        "roles/cloudsql.client",
    )

    command = run_command.call_args.args[0]
    assert "add-iam-policy-binding" in command
    assert "roles/cloudsql.client" in command
    assert "serviceAccount:" in " ".join(command)


def test_bind_secret_accessor(monkeypatch: pytest.MonkeyPatch) -> None:
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    provision.bind_secret_accessor(
        "test-sabor-da-terra",
        "jwt-secret-key",
        "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com",
    )

    command = run_command.call_args.args[0]
    assert "secrets" in command
    assert "jwt-secret-key" in command
    assert "roles/secretmanager.secretAccessor" in command


def test_configure_stage_5_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "enable_stage_5_apis", Mock())
    monkeypatch.setattr(
        provision,
        "ensure_service_accounts",
        Mock(
            return_value={
                "api": "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com",
                "tasks": "sabor-da-terra-tasks@test-sabor-da-terra.iam.gserviceaccount.com",
                "scheduler":
                    "sabor-da-terra-scheduler@test-sabor-da-terra.iam.gserviceaccount.com",
            }
        ),
    )
    monkeypatch.setattr(provision, "ensure_secret", Mock(return_value=False))
    bind_project_role = Mock()
    bind_secret_accessor = Mock()
    monkeypatch.setattr(provision, "bind_project_role", bind_project_role)
    monkeypatch.setattr(provision, "bind_secret_accessor", bind_secret_accessor)
    monkeypatch.setattr(provision.secrets, "token_urlsafe", Mock(return_value="generated"))

    config = {
        "inference": {
            "mode": "vertex",
        }
    }

    emails = provision.configure_stage_5("test-sabor-da-terra", config)

    assert emails["api"].startswith("sabor-da-terra-api@")
    roles = [call.args[2] for call in bind_project_role.call_args_list]
    assert "roles/aiplatform.user" in roles
    assert "roles/cloudsql.client" in roles
    assert "roles/cloudtasks.enqueuer" in roles
    secret_names = [call.args[1] for call in bind_secret_accessor.call_args_list]
    assert "database-url" in secret_names
    assert "jwt-secret-key" in secret_names
    assert "gemini-api-key" not in secret_names


def test_configure_stage_5_developer_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "enable_stage_5_apis", Mock())
    monkeypatch.setattr(
        provision,
        "ensure_service_accounts",
        Mock(
            return_value={
                "api": "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com",
                "tasks": "sabor-da-terra-tasks@test-sabor-da-terra.iam.gserviceaccount.com",
                "scheduler":
                    "sabor-da-terra-scheduler@test-sabor-da-terra.iam.gserviceaccount.com",
            }
        ),
    )
    monkeypatch.setattr(provision, "ensure_secret", Mock(return_value=False))
    monkeypatch.setattr(provision, "get_secret", Mock(return_value=None))
    monkeypatch.setattr(provision, "bind_project_role", Mock())
    monkeypatch.setattr(provision, "bind_secret_accessor", Mock())
    monkeypatch.setattr(provision.secrets, "token_urlsafe", Mock(return_value="generated"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(provision, "getpass", Mock(return_value=""))

    config = {
        "inference": {
            "mode": "developer",
        }
    }

    with pytest.raises(InfraError, match="GEMINI_API_KEY"):
        provision.configure_stage_5("test-sabor-da-terra", config)


def test_configure_stage_5_preserves_gemini_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "enable_stage_5_apis", Mock())
    monkeypatch.setattr(
        provision,
        "ensure_service_accounts",
        Mock(
            return_value={
                "api": "sabor-da-terra-api@test-sabor-da-terra.iam.gserviceaccount.com",
                "tasks": "sabor-da-terra-tasks@test-sabor-da-terra.iam.gserviceaccount.com",
                "scheduler":
                    "sabor-da-terra-scheduler@test-sabor-da-terra.iam.gserviceaccount.com",
            }
        ),
    )
    monkeypatch.setattr(provision, "ensure_secret", Mock(return_value=False))
    monkeypatch.setattr(provision, "get_secret", Mock(return_value={"name": "existing"}))
    monkeypatch.setattr(provision, "bind_project_role", Mock())
    bind_secret_accessor = Mock()
    monkeypatch.setattr(provision, "bind_secret_accessor", bind_secret_accessor)
    monkeypatch.setattr(provision.secrets, "token_urlsafe", Mock(return_value="generated"))

    provision.configure_stage_5(
        "test-sabor-da-terra",
        {"inference": {"mode": "developer"}},
    )

    secret_names = [call.args[1] for call in bind_secret_accessor.call_args_list]
    assert "gemini-api-key" in secret_names
