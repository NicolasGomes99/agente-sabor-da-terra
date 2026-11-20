import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common


def valid_config(project_id: str = "test-sabor-da-terra") -> dict:
    return {
        "project_id": project_id,
        "region": "us-central1",
        "database": {
            "instance_name": "sabor-da-terra-db",
            "database_name": "sabor_da_terra",
            "tier": "db-f1-micro",
        },
        "artifacts": {"repository_name": "sabor-da-terra"},
        "storage": {"bucket_name": None},
        "cloud_run": {"service_name": "sabor-da-terra-api"},
        "inference": {
            "mode": "vertex",
            "model": "gemini-3.8-flash",
            "location": "global",
        },
        "budget": {
            "amount_usd": 1.0,
            "alert_thresholds": [0.5, 0.8, 1.0],
        },
    }


def test_load_missing_config(tmp_path: Path) -> None:
    with pytest.raises(common.InfraError, match="Configuration file not found"):
        common.load_config(tmp_path / "config.local.json")


def test_load_invalid_json(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text("{", encoding="utf-8")

    with pytest.raises(common.InfraError, match="Invalid JSON"):
        common.load_config(config_path)


def test_load_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.json"
    config_path.write_text(json.dumps(valid_config()), encoding="utf-8")

    assert common.load_config(config_path) == valid_config()


@pytest.mark.parametrize("project_id", ["", "sabor-da-terra"])
def test_validate_config_requires_unique_project_id(project_id: str) -> None:
    config = valid_config(project_id)

    with pytest.raises(common.InfraError, match="unique project_id"):
        common.validate_config(config)


def test_validate_config_rejects_wrong_region() -> None:
    config = valid_config()
    config["region"] = "southamerica-east1"

    with pytest.raises(common.InfraError, match="us-central1"):
        common.validate_config(config)


@pytest.mark.parametrize("mode", ["developer", "vertex"])
def test_validate_config_accepts_supported_inference_modes(mode: str) -> None:
    config = valid_config()
    config["inference"]["mode"] = mode

    common.validate_config(config)


def test_validate_config_rejects_unknown_inference_mode() -> None:
    config = valid_config()
    config["inference"]["mode"] = "fallback"

    with pytest.raises(common.InfraError, match="inference.mode"):
        common.validate_config(config)


def test_validate_config_rejects_budget_threshold_changes() -> None:
    config = valid_config()
    config["budget"]["alert_thresholds"] = [0.5, 1.0]

    with pytest.raises(common.InfraError, match=r"\[0.5, 0.8, 1.0\]"):
        common.validate_config(config)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["gcloud", "secrets", "add", "database-password"], "[REDACTED]"),
        (["gcloud", "--project=test-sabor-da-terra"], "test-sabor-da-terra"),
    ],
)
def test_format_command_redacts_sensitive_values(
    command: list[str],
    expected: str,
) -> None:
    formatted = common.format_command(command)
    assert expected in formatted


def test_require_commands_reports_missing_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common.shutil, "which", lambda name: None)

    with pytest.raises(common.InfraError, match="gcloud"):
        common.require_commands(["gcloud"])


def test_require_git_clean_accepts_clean_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status", "--porcelain"],
        returncode=0,
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(common, "run_command", Mock(return_value=completed))

    common.require_git_clean()


def test_require_git_clean_rejects_dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(
        args=["git", "status", "--porcelain"],
        returncode=0,
        stdout=" M backend/dockerfile\n",
        stderr="",
    )
    monkeypatch.setattr(common, "run_command", Mock(return_value=completed))

    with pytest.raises(common.InfraError, match="working tree is not clean"):
        common.require_git_clean()
