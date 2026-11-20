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

import provision
from common import InfraError


PROJECT_ID = "test-sabor-da-terra"
PROJECT_NUMBER = "123456"
BILLING_ACCOUNT = "ABCDEF-123456-ABCDEF"
OTHER_BILLING_ACCOUNT = "FEDCBA-654321-FEDCBA"


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


@pytest.fixture
def config():
    return {
        "project_id": PROJECT_ID,
        "region": "us-central1",
        "billing_account_id": BILLING_ACCOUNT,
        "artifacts": {
            "repository_name": "sabor-da-terra",
        },
        "storage": {
            "bucket_name": None,
        },
        "inference": {
            "mode": "vertex",
        },
        "budget": {
            "currency": "USD",
            "amount": 1.0,
        },
    }


@pytest.fixture
def budget():
    return {
        "name": (
            f"billingAccounts/{BILLING_ACCOUNT}"
            "/budgets/test-budget"
        ),
        "displayName": f"Sabor da Terra - {PROJECT_ID}",
        "budgetFilter": {
            "projects": [f"projects/{PROJECT_NUMBER}"],
            "calendarPeriod": "MONTH",
        },
        "amount": {
            "specifiedAmount": {
                "currencyCode": "USD",
                "units": "1",
                "nanos": 0,
            },
        },
        "thresholdRules": [
            {
                "thresholdPercent": threshold,
                "spendBasis": "CURRENT_SPEND",
            }
            for threshold in (0.5, 0.8, 1.0)
        ],
    }


def test_run_json(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                json.dumps({"name": "resource"})
            )
        ),
    )

    assert provision.run_json(
        ["gcloud", "test"]
    ) == {"name": "resource"}


def test_run_json_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed("invalid")),
    )

    with pytest.raises(
        InfraError,
        match="Invalid JSON",
    ):
        provision.run_json(
            ["gcloud", "test"]
        )


def test_get_active_account(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                "employee@example.com\n"
            )
        ),
    )

    assert (
        provision.get_active_account()
        == "employee@example.com"
    )


def test_get_active_account_requires_login(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(return_value=completed()),
    )

    with pytest.raises(
        InfraError,
        match="gcloud auth login",
    ):
        provision.get_active_account()


def test_verify_adc(monkeypatch, capsys):
    run_command = Mock(
        return_value=completed(
            "sensitive-access-token"
        )
    )

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.verify_adc()

    assert run_command.call_args.kwargs[
        "capture_output"
    ] is True

    assert (
        "sensitive-access-token"
        not in capsys.readouterr().out
    )


def test_get_project_returns_existing(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                json.dumps(
                    {"lifecycleState": "ACTIVE"}
                )
            )
        ),
    )

    project = provision.get_project(PROJECT_ID)

    assert project is not None
    assert project["lifecycleState"] == "ACTIVE"


def test_get_project_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                returncode=1,
                stderr="NOT_FOUND: project not found",
            )
        ),
    )

    assert provision.get_project(PROJECT_ID) is None


def test_project_lookup_rejects_permission_error(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_command",
        Mock(
            return_value=completed(
                returncode=1,
                stderr="PERMISSION_DENIED",
            )
        ),
    )

    with pytest.raises(InfraError):
        provision.get_project(PROJECT_ID)


def test_ensure_project_reuses_active_project(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[{"projectId": PROJECT_ID}]),
    )

    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(
            return_value={
                "lifecycleState": "ACTIVE",
            }
        ),
    )

    confirm = Mock()

    monkeypatch.setattr(
        provision,
        "confirm",
        confirm,
    )

    assert provision.ensure_project(PROJECT_ID) is False

    confirm.assert_not_called()


@pytest.mark.parametrize(
    "lifecycle",
    [
        "DELETE_REQUESTED",
        "DELETE_IN_PROGRESS",
        "PENDING_DELETION",
    ],
)
def test_ensure_project_rejects_inactive_project(
    monkeypatch,
    lifecycle,
):
    monkeypatch.setattr(
    provision,
    "run_json",
    Mock(return_value=[{"projectId": PROJECT_ID}]),
)
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(
            return_value={
                "lifecycleState": lifecycle,
            }
        ),
    )

    with pytest.raises(
        InfraError,
        match=lifecycle,
    ):
        provision.ensure_project(PROJECT_ID)


def test_ensure_project_creates_after_confirmation(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(return_value=None),
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

    assert provision.ensure_project(PROJECT_ID) is True

    confirm.assert_called_once()

    command = run_command.call_args.args[0]

    assert command[:3] == [
        "gcloud",
        "projects",
        "create",
    ]

    assert PROJECT_ID in command


def test_confirmation_rejects_default_answer(monkeypatch):
    monkeypatch.setattr(
        "builtins.input",
        lambda _: "",
    )

    with pytest.raises(
        InfraError,
        match="cancelled",
    ):
        provision.confirm("Create resource?")


def test_enable_required_apis(monkeypatch):
    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.enable_required_apis(PROJECT_ID)

    command = run_command.call_args.args[0]

    assert command[:3] == [
        "gcloud",
        "services",
        "enable",
    ]

    assert "cloudresourcemanager.googleapis.com" in command
    assert "billingbudgets.googleapis.com" in command
    assert PROJECT_ID in command


def mock_billing(
    monkeypatch,
    *,
    currency="USD",
    linked_account=BILLING_ACCOUNT,
    enabled=True,
):
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(
            side_effect=[
                [
                    {
                        "name": (
                            f"billingAccounts/{BILLING_ACCOUNT}"
                        ),
                        "open": True,
                    }
                ],
                {
                    "currencyCode": currency,
                },
            ]
        ),
    )

    monkeypatch.setattr(
        provision,
        "describe_json",
        Mock(
            return_value={
                "billingAccountName": (
                    f"billingAccounts/{linked_account}"
                    if linked_account
                    else ""
                ),
                "billingEnabled": enabled,
            }
        ),
    )


def test_ensure_billing_reuses_matching_account(monkeypatch):
    mock_billing(monkeypatch)

    assert provision.ensure_billing_account(
        PROJECT_ID,
        BILLING_ACCOUNT,
    ) == "USD"


def test_ensure_billing_rejects_different_account(monkeypatch):
    mock_billing(
        monkeypatch,
        linked_account=OTHER_BILLING_ACCOUNT,
    )

    with pytest.raises(
        InfraError,
        match="Refuse to relink",
    ):
        provision.ensure_billing_account(
            PROJECT_ID,
            BILLING_ACCOUNT,
        )


def test_ensure_billing_rejects_currency_mismatch(monkeypatch):
    mock_billing(
        monkeypatch,
        currency="BRL",
    )

    with pytest.raises(
        InfraError,
        match="uses BRL",
    ):
        provision.ensure_billing_account(
            PROJECT_ID,
            BILLING_ACCOUNT,
        )


def test_ensure_billing_accepts_brl(monkeypatch):
    mock_billing(
        monkeypatch,
        currency="BRL",
    )

    assert provision.ensure_billing_account(
        PROJECT_ID,
        BILLING_ACCOUNT,
        expected_currency="BRL",
    ) == "BRL"


def test_ensure_billing_rejects_disabled_billing(monkeypatch):
    mock_billing(
        monkeypatch,
        enabled=False,
    )

    with pytest.raises(
        InfraError,
        match="billing is disabled",
    ):
        provision.ensure_billing_account(
            PROJECT_ID,
            BILLING_ACCOUNT,
        )


def test_ensure_billing_rejects_unavailable_account(monkeypatch):
    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[]),
    )

    with pytest.raises(
        InfraError,
        match="unavailable or closed",
    ):
        provision.ensure_billing_account(
            PROJECT_ID,
            BILLING_ACCOUNT,
        )


def test_ensure_billing_links_after_confirmation(monkeypatch):
    mock_billing(
        monkeypatch,
        linked_account=None,
        enabled=False,
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

    assert provision.ensure_billing_account(
        PROJECT_ID,
        BILLING_ACCOUNT,
    ) == "USD"

    confirm.assert_called_once()

    command = run_command.call_args.args[0]

    assert command[:4] == [
        "gcloud",
        "billing",
        "projects",
        "link",
    ]

    assert PROJECT_ID in command
    assert BILLING_ACCOUNT in command


def test_verify_valid_budget(budget):
    problems = provision.verify_project_budget(
        budget,
        {
            f"projects/{PROJECT_ID}",
            f"projects/{PROJECT_NUMBER}",
        },
        1.0,
        "USD",
    )

    assert problems == []


def test_rejects_budget_shared_with_other_projects(budget):
    budget["budgetFilter"]["projects"].append(
        "projects/another-project"
    )

    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        1.0,
        "USD",
    )

    assert problems


def test_rejects_budget_limited_to_services(budget):
    budget["budgetFilter"]["services"] = [
        "services/example"
    ]

    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        1.0,
        "USD",
    )

    assert problems


def test_rejects_wrong_budget_currency(budget):
    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        1.0,
        "BRL",
    )

    assert problems


def test_rejects_wrong_budget_amount(budget):
    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        5.0,
        "USD",
    )

    assert problems


def test_rejects_wrong_budget_thresholds(budget):
    budget["thresholdRules"] = [
        {
            "thresholdPercent": 1.0,
            "spendBasis": "CURRENT_SPEND",
        }
    ]

    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        1.0,
        "USD",
    )

    assert problems


@pytest.mark.parametrize(
    "field",
    ["notificationsRule", "allUpdatesRule"],
)
def test_rejects_disabled_budget_notifications(budget, field):
    budget[field] = {
        "disableDefaultIamRecipients": True,
    }

    problems = provision.verify_project_budget(
        budget,
        {f"projects/{PROJECT_NUMBER}"},
        1.0,
        "USD",
    )

    assert (
        "Default IAM budget notifications are disabled."
        in problems
    )


def test_ensure_project_budget_reuses_existing(
    monkeypatch,
    budget,
):
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(
            return_value={
                "projectNumber": PROJECT_NUMBER,
            }
        ),
    )

    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[budget]),
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

    provision.ensure_project_budget(
        PROJECT_ID,
        BILLING_ACCOUNT,
        1.0,
        "USD",
    )

    confirm.assert_not_called()
    run_command.assert_not_called()


def test_ensure_project_budget_rejects_incompatible(
    monkeypatch,
    budget,
):
    budget["amount"]["specifiedAmount"]["units"] = "5"

    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(
            return_value={
                "projectNumber": PROJECT_NUMBER,
            }
        ),
    )

    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[budget]),
    )

    with pytest.raises(
        InfraError,
        match="does not match",
    ):
        provision.ensure_project_budget(
            PROJECT_ID,
            BILLING_ACCOUNT,
            1.0,
            "USD",
        )


@pytest.mark.parametrize(
    ("currency", "amount", "expected"),
    [
        ("USD", 1.0, "1.00USD"),
        ("BRL", 6.0, "6.00BRL"),
    ],
)
def test_ensure_project_budget_creates_expected_budget(
    monkeypatch,
    currency,
    amount,
    expected,
):
    monkeypatch.setattr(
        provision,
        "get_project",
        Mock(return_value=None),
    )

    monkeypatch.setattr(
        provision,
        "run_json",
        Mock(return_value=[]),
    )

    monkeypatch.setattr(
        provision,
        "confirm",
        Mock(),
    )

    run_command = Mock()

    monkeypatch.setattr(
        provision,
        "run_command",
        run_command,
    )

    provision.ensure_project_budget(
        PROJECT_ID,
        BILLING_ACCOUNT,
        amount,
        currency,
    )

    command = run_command.call_args.args[0]

    assert expected in command
    assert "month" in command
    assert f"projects/{PROJECT_ID}" in command

    thresholds = [
        argument
        for argument in command
        if argument.startswith(
            "basis=current-spend,percent="
        )
    ]

    assert thresholds == [
        "basis=current-spend,percent=0.5",
        "basis=current-spend,percent=0.8",
        "basis=current-spend,percent=1.0",
    ]


def test_provision_respects_operation_order(
    monkeypatch,
    config,
):
    operations = Mock()

    names = [
        "require_commands",
        "get_active_account",
        "confirm",
        "verify_adc",
        "ensure_project",
        "ensure_billing_account",
        "enable_required_apis",
        "ensure_project_budget",
        "configure_stage_5",
        "configure_stage6",
        "configure_stage7",
    ]

    for name in names:
        monkeypatch.setattr(
            provision,
            name,
            getattr(operations, name),
        )

    operations.get_active_account.return_value = (
        "employee@example.com"
    )

    operations.ensure_billing_account.return_value = "USD"

    operations.configure_stage_5.return_value = {
        "api": "api@example.com",
    }

    provision.provision(config)

    actual_order = [
        call[0]
        for call in operations.mock_calls
    ]

    assert actual_order == names


def test_provision_stops_when_budget_fails(
    monkeypatch,
    config,
):
    for name in [
        "require_commands",
        "get_active_account",
        "confirm",
        "verify_adc",
        "ensure_project",
        "enable_required_apis",
    ]:
        monkeypatch.setattr(
            provision,
            name,
            Mock(),
        )

    monkeypatch.setattr(
        provision,
        "ensure_billing_account",
        Mock(return_value="USD"),
    )

    monkeypatch.setattr(
        provision,
        "ensure_project_budget",
        Mock(
            side_effect=InfraError(
                "Budget configuration failed."
            )
        ),
    )

    stage5 = Mock()
    stage6 = Mock()
    stage7 = Mock()

    monkeypatch.setattr(
        provision,
        "configure_stage_5",
        stage5,
    )

    monkeypatch.setattr(
        provision,
        "configure_stage6",
        stage6,
    )

    monkeypatch.setattr(
        provision,
        "configure_stage7",
        stage7,
    )

    with pytest.raises(
        InfraError,
        match="Budget configuration failed",
    ):
        provision.provision(config)

    stage5.assert_not_called()
    stage6.assert_not_called()
    stage7.assert_not_called()