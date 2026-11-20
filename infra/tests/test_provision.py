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


def test_get_active_account(monkeypatch: pytest.MonkeyPatch) -> None:
    run_command = Mock(return_value=completed("employee@example.com\n"))
    monkeypatch.setattr(provision, "run_command", run_command)

    assert provision.get_active_account() == "employee@example.com"


def test_get_active_account_requires_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "run_command", Mock(return_value=completed("")))

    with pytest.raises(InfraError, match="gcloud auth login"):
        provision.get_active_account()


def test_get_project_returns_existing_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed(json.dumps({"lifecycleState": "ACTIVE"}))),
    )

    assert provision.get_project("test-sabor-da-terra")["lifecycleState"] == "ACTIVE"


def test_get_project_returns_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed("not found", returncode=1)),
    )

    assert provision.get_project("test-sabor-da-terra") is None


def test_ensure_project_reuses_active_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(return_value={"lifecycleState": "ACTIVE"}),
    )
    confirm = Mock()
    monkeypatch.setattr(provision, "confirm", confirm)

    assert provision.ensure_project("test-sabor-da-terra") is False
    confirm.assert_not_called()


@pytest.mark.parametrize(
    "lifecycle",
    ["DELETE_REQUESTED", "DELETE_IN_PROGRESS", "PENDING_DELETION"],
)
def test_ensure_project_rejects_non_active_project(
    lifecycle: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(return_value={"lifecycleState": lifecycle}),
    )

    with pytest.raises(InfraError, match=lifecycle):
        provision.ensure_project("test-sabor-da-terra")


def test_ensure_project_creates_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "get_project", Mock(return_value=None))
    confirm = Mock()
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "confirm", confirm)
    monkeypatch.setattr(provision, "run_command", run_command)

    assert provision.ensure_project("test-sabor-da-terra") is True
    confirm.assert_called_once()
    run_command.assert_called_once()


def test_enable_required_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    provision.enable_required_apis("test-sabor-da-terra")

    command = run_command.call_args.args[0]
    assert command[:4] == ["gcloud", "services", "enable", *command[3:4]]
    assert "cloudresourcemanager.googleapis.com" in command
    assert "billingbudgets.googleapis.com" in command


def test_ensure_billing_account_reuses_matching_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(
            return_value=[
                {"name": "billingAccounts/XXXXXX-XXXXXX-XXXXXX", "open": True}
            ]
        ),
    )
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                json.dumps(
                    {
                        "billingAccountName":
                            "billingAccounts/XXXXXX-XXXXXX-XXXXXX"
                    }
                )
            )
        ),
    )

    provision.ensure_billing_account(
        "test-sabor-da-terra",
        "XXXXXX-XXXXXX-XXXXXX",
    )


def test_ensure_billing_account_rejects_different_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(
            return_value=[
                {"name": "billingAccounts/XXXXXX-XXXXXX-XXXXXX", "open": True}
            ]
        ),
    )
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                json.dumps(
                    {
                        "billingAccountName":
                            "billingAccounts/YYYYYY-YYYYYY-YYYYYY"
                    }
                )
            )
        ),
    )

    with pytest.raises(InfraError, match="Refuse to relink"):
        provision.ensure_billing_account(
            "test-sabor-da-terra",
            "XXXXXX-XXXXXX-XXXXXX",
        )


def test_ensure_billing_account_rejects_unavailable_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "run_json", Mock(return_value=[]))

    with pytest.raises(InfraError, match="unavailable or closed"):
        provision.ensure_billing_account(
            "test-sabor-da-terra",
            "XXXXXX-XXXXXX-XXXXXX",
        )


def test_ensure_project_budget_reuses_existing_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(
            return_value=[
                {"displayName": "Sabor da Terra - test-sabor-da-terra"}
            ]
        ),
    )
    confirm = Mock()
    monkeypatch.setattr(provision, "confirm", confirm)

    provision.ensure_project_budget(
        "test-sabor-da-terra",
        "XXXXXX-XXXXXX-XXXXXX",
        1.0,
    )
    confirm.assert_not_called()


def test_ensure_project_budget_creates_expected_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provision, "run_json", Mock(return_value=[]))
    monkeypatch.setattr(provision, "confirm", Mock())
    run_command = Mock(return_value=completed())
    monkeypatch.setattr(provision, "run_command", run_command)

    provision.ensure_project_budget(
        "test-sabor-da-terra",
        "XXXXXX-XXXXXX-XXXXXX",
        1.0,
    )

    command = run_command.call_args.args[0]
    assert "1.00USD" in command
    assert "projects/test-sabor-da-terra" in command
    assert "month" in command
    thresholds = [arg for arg in command if arg.startswith("basis=current-spend,percent=")]
    assert thresholds == [
        "basis=current-spend,percent=0.5",
        "basis=current-spend,percent=0.8",
        "basis=current-spend,percent=1.0",
    ]
