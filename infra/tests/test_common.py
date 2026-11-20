import json
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


@pytest.fixture(autouse=True)
def clear_secrets():
    common.clear_registered_secrets()

    yield

    common.clear_registered_secrets()


def valid_config(
    project_id: str = "test-sabor-da-terra",
) -> dict:
    return {
        "project_id": project_id,
        "region": "us-central1",
        "billing_account_id": "ABCDEF-123456-ABCDEF",
        "database": {
            "instance_name": "sabor-da-terra-db",
            "database_name": "sabor_da_terra",
            "tier": "db-f1-micro",
            "storage_size_gb": 10,
            "backup_enabled": False,
            "deletion_protection": True,
            "admin_user": "postgres",
            "migrator_user": "sabor_da_terra_migrator",
            "application_user": "sabor_da_terra_app",
        },
        "artifacts": {
            "repository_name": "sabor-da-terra",
        },
        "storage": {
            "bucket_name": None,
        },
        "cloud_run": {
            "service_name": "sabor-da-terra-api",
            "cpu": "1",
            "memory": "512Mi",
            "min_instances": 0,
            "max_instances": 2,
            "concurrency": 10,
            "timeout_seconds": 300,
            "billing": "request-based",
        },
        "inference": {
            "mode": "vertex",
            "model": "gemini-3.8-flash",
            "location": "global",
        },
        "budget": {
            "currency": "USD",
            "amount": 1.0,
            "alert_thresholds": [0.5, 0.8, 1.0],
        },
    }


def completed(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_load_missing_config(tmp_path: Path):
    with pytest.raises(
        common.InfraError,
        match="Configuration file not found",
    ):
        common.load_config(
            tmp_path / "config.local.json"
        )


def test_load_invalid_json(tmp_path: Path):
    path = tmp_path / "config.local.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(
        common.InfraError,
        match="Invalid JSON",
    ):
        common.load_config(path)


def test_load_non_object_config(tmp_path: Path):
    path = tmp_path / "config.local.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(
        common.InfraError,
        match="JSON object",
    ):
        common.load_config(path)


def test_load_valid_config(tmp_path: Path):
    path = tmp_path / "config.local.json"

    path.write_text(
        json.dumps(valid_config()),
        encoding="utf-8",
    )

    assert common.load_config(path) == valid_config()


@pytest.mark.parametrize(
    "project_id",
    ["", "sabor-da-terra"],
)
def test_requires_unique_project_id(project_id):
    with pytest.raises(
        common.InfraError,
        match="unique project_id",
    ):
        common.validate_config(
            valid_config(project_id)
        )


@pytest.mark.parametrize(
    "project_id",
    [
        "UPPERCASE",
        "has_underscore",
        "-leading",
        "trailing-",
        "ab",
        "toolong-project-id-toolong-project-id",
    ],
)
def test_rejects_invalid_project_id(project_id):
    with pytest.raises(
        common.InfraError,
        match="valid Google Cloud Project ID",
    ):
        common.validate_config(
            valid_config(project_id)
        )


def test_accepts_valid_config():
    common.validate_config(valid_config())


@pytest.mark.parametrize(
    "account",
    [
        "",
        "XXXXXX-XXXXXX-XXXXXX",
        "invalid-account",
    ],
)
def test_rejects_invalid_billing_account(account):
    config = valid_config()
    config["billing_account_id"] = account

    with pytest.raises(
        common.InfraError,
        match="billing_account_id",
    ):
        common.validate_config(config)


def test_rejects_wrong_region():
    config = valid_config()
    config["region"] = "southamerica-east1"

    with pytest.raises(
        common.InfraError,
        match="us-central1",
    ):
        common.validate_config(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instance_name", "invalid_instance"),
        ("instance_name", "1-instance"),
        ("database_name", "invalid-database"),
        ("database_name", "postgres"),
        ("database_name", "template1"),
        ("storage_size_gb", 5),
        ("storage_size_gb", True),
        ("backup_enabled", True),
        ("deletion_protection", False),
        ("admin_user", "admin"),
        ("application_user", "postgres"),
        ("application_user", "pg_read_all_data"),
        ("migrator_user", "cloudsqlsuperuser"),
        ("tier", "db-custom-2-7680"),
    ],
)
def test_rejects_invalid_database_config(field, value):
    config = valid_config()
    config["database"][field] = value

    with pytest.raises(common.InfraError):
        common.validate_config(config)


def test_rejects_duplicate_database_users():
    config = valid_config()

    config["database"]["application_user"] = (
        config["database"]["migrator_user"]
    )

    with pytest.raises(
        common.InfraError,
        match="must be different",
    ):
        common.validate_config(config)


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "INVALID",
        "invalid_repository",
    ],
)
def test_rejects_invalid_repository(repository):
    config = valid_config()

    config["artifacts"]["repository_name"] = (
        repository
    )

    with pytest.raises(
        common.InfraError,
        match="repository_name",
    ):
        common.validate_config(config)


@pytest.mark.parametrize(
    "bucket",
    [
        "",
        "INVALID",
        "-invalid",
        "invalid-",
        "ab",
    ],
)
def test_rejects_invalid_bucket(bucket):
    config = valid_config()
    config["storage"]["bucket_name"] = bucket

    with pytest.raises(
        common.InfraError,
        match="bucket_name",
    ):
        common.validate_config(config)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("service_name", "invalid_service"),
        ("cpu", "2"),
        ("memory", "4Gi"),
        ("min_instances", 1),
        ("max_instances", 3),
        ("max_instances", 0),
        ("max_instances", True),
        ("concurrency", 0),
        ("concurrency", 11),
        ("timeout_seconds", 301),
        ("billing", "instance-based"),
    ],
)
def test_rejects_invalid_cloud_run_config(field, value):
    config = valid_config()
    config["cloud_run"][field] = value

    with pytest.raises(
        common.InfraError,
        match="cloud_run",
    ):
        common.validate_config(config)


def test_accepts_cloud_run_memory_increase():
    config = valid_config()
    config["cloud_run"]["memory"] = "1Gi"

    common.validate_config(config)


@pytest.mark.parametrize(
    "mode",
    ["developer", "vertex"],
)
def test_accepts_inference_modes(mode):
    config = valid_config()
    config["inference"]["mode"] = mode

    common.validate_config(config)


@pytest.mark.parametrize(
    "mode",
    [None, "", "fallback"],
)
def test_rejects_invalid_inference_mode(mode):
    config = valid_config()
    config["inference"]["mode"] = mode

    with pytest.raises(
        common.InfraError,
        match="inference.mode",
    ):
        common.validate_config(config)


def test_rejects_invalid_model():
    config = valid_config()
    config["inference"]["model"] = ""

    with pytest.raises(
        common.InfraError,
        match="inference.model",
    ):
        common.validate_config(config)


def test_rejects_unplanned_inference_location():
    config = valid_config()

    config["inference"]["location"] = (
        "us-east1"
    )

    with pytest.raises(
        common.InfraError,
        match="inference.location",
    ):
        common.validate_config(config)


@pytest.mark.parametrize(
    "amount",
    [
        0,
        -1,
        "1",
        True,
        1.001,
        float("inf"),
        float("nan"),
    ],
)
def test_rejects_invalid_budget_amount(amount):
    config = valid_config()
    config["budget"]["amount"] = amount

    with pytest.raises(
        common.InfraError,
        match="budget.amount",
    ):
        common.validate_config(config)


def test_accepts_brl_budget():
    config = valid_config()

    config["budget"]["currency"] = "BRL"
    config["budget"]["amount"] = 6.0

    common.validate_config(config)


def test_accepts_legacy_usd_budget():
    config = valid_config()

    config["budget"] = {
        "amount_usd": 1.0,
        "alert_thresholds": [0.5, 0.8, 1.0],
    }

    common.validate_config(config)


def test_rejects_mixed_budget_fields():
    config = valid_config()
    config["budget"]["amount_usd"] = 1.0

    with pytest.raises(
        common.InfraError,
        match="not both",
    ):
        common.validate_config(config)


def test_rejects_invalid_budget_thresholds():
    config = valid_config()

    config["budget"]["alert_thresholds"] = [
        0.5,
        1.0,
    ]

    with pytest.raises(
        common.InfraError,
        match="alert_thresholds",
    ):
        common.validate_config(config)


def test_redacts_registered_secret():
    common.register_secret(
        "my-sensitive-value"
    )

    result = common.redact_text(
        "Value: my-sensitive-value"
    )

    assert "my-sensitive-value" not in result
    assert "[REDACTED]" in result


def test_redacts_database_url():
    result = common.redact_text(
        "postgresql+asyncpg://app:password123@localhost/db"
    )

    assert "password123" not in result
    assert "[REDACTED]" in result


@pytest.mark.parametrize(
    "command",
    [
        [
            "gcloud",
            "--root-password=secret123",
        ],
        [
            "gcloud",
            "--password",
            "secret123",
        ],
        [
            "gcloud",
            "--api-key=secret123",
        ],
    ],
)
def test_format_command_redacts_secrets(command):
    result = common.format_command(command)

    assert "secret123" not in result
    assert "[REDACTED]" in result


def test_format_command_preserves_project():
    result = common.format_command(
        [
            "gcloud",
            "--project=test-sabor-da-terra",
        ]
    )

    assert "test-sabor-da-terra" in result


def test_missing_resource_detected():
    result = completed(
        stderr="NOT_FOUND: resource not found",
        returncode=1,
    )

    assert common.is_missing_resource(
        result,
        "Resource lookup",
    )


@pytest.mark.parametrize(
    "stderr",
    [
        "PERMISSION_DENIED: resource not found",
        "UNAUTHENTICATED",
        "Network connection failed",
        "403 Forbidden",
    ],
)
def test_missing_resource_does_not_hide_errors(stderr):
    result = completed(
        stderr=stderr,
        returncode=1,
    )

    with pytest.raises(common.InfraError):
        common.is_missing_resource(
            result,
            "Resource lookup",
        )


def test_require_commands_reports_missing_tools(
    monkeypatch,
):
    monkeypatch.setattr(
        common.shutil,
        "which",
        lambda name: None,
    )

    with pytest.raises(
        common.InfraError,
        match="gcloud",
    ):
        common.require_commands(
            ["gcloud"]
        )


def test_resolve_missing_command(monkeypatch):
    monkeypatch.setattr(
        common.shutil,
        "which",
        lambda name: None,
    )

    with pytest.raises(
        common.InfraError,
        match="Required executable not found",
    ):
        common.resolve_command(
            ["missing-command"]
        )


def test_run_command_passes_environment(
    monkeypatch,
):
    monkeypatch.setattr(
        common,
        "resolve_command",
        lambda command: list(command),
    )

    run = Mock(
        return_value=completed(
            stdout="ok"
        )
    )

    monkeypatch.setattr(
        common.subprocess,
        "run",
        run,
    )

    result = common.run_command(
        ["test-command"],
        env={
            "TEST_VARIABLE": "value",
        },
        capture_output=True,
    )

    assert result.stdout == "ok"

    kwargs = run.call_args.kwargs

    assert (
        kwargs["env"]["TEST_VARIABLE"]
        == "value"
    )

    assert kwargs["shell"] is False


def test_run_command_sanitizes_error(
    monkeypatch,
):
    monkeypatch.setattr(
        common,
        "resolve_command",
        lambda command: list(command),
    )

    monkeypatch.setattr(
        common.subprocess,
        "run",
        Mock(
            return_value=completed(
                stderr="Failure: secret-value",
                returncode=1,
            )
        ),
    )

    with pytest.raises(
        common.InfraError
    ) as error:
        common.run_command(
            ["test-command"],
            secrets=["secret-value"],
        )

    assert (
        "secret-value"
        not in str(error.value)
    )

    assert (
        "[REDACTED]"
        in str(error.value)
    )


def test_run_command_sanitizes_output(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        common,
        "resolve_command",
        lambda command: list(command),
    )

    monkeypatch.setattr(
        common.subprocess,
        "run",
        Mock(
            return_value=completed(
                stdout="secret-value",
                stderr="secret-value",
            )
        ),
    )

    common.run_command(
        ["test-command"],
        secrets=["secret-value"],
    )

    output = capsys.readouterr()

    assert "secret-value" not in output.out
    assert "secret-value" not in output.err


def test_require_git_clean_accepts_clean_tree(
    monkeypatch,
):
    monkeypatch.setattr(
        common,
        "run_command",
        Mock(return_value=completed()),
    )

    common.require_git_clean()


def test_require_git_clean_rejects_dirty_tree(
    monkeypatch,
):
    monkeypatch.setattr(
        common,
        "run_command",
        Mock(
            return_value=completed(
                stdout=" M backend/dockerfile\n"
            )
        ),
    )

    with pytest.raises(
        common.InfraError,
        match="working tree is not clean",
    ):
        common.require_git_clean()