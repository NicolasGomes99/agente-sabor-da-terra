import json
from typing import Any

from common import (
    InfraError,
    base_parser,
    main_entry,
    require_commands,
    run_command,
)


STAGE_4_APIS = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
    "iam.googleapis.com",
]


def run_json(command: list[str]) -> Any:
    result = run_command(command, check=True, capture_output=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InfraError(
            f"Google Cloud returned invalid JSON for: {' '.join(command)}"
        ) from error


def get_active_account() -> str:
    result = run_command(
        ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
        check=True,
        capture_output=True,
    )
    account = result.stdout.strip().splitlines()
    if not account:
        raise InfraError("No active gcloud account. Run gcloud auth login.")
    return account[0]


def get_project(project_id: str) -> dict | None:
    result = run_command(
        [
            "gcloud",
            "projects",
            "describe",
            project_id,
            "--format=json",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InfraError("gcloud returned invalid project data.") from error


def confirm(message: str) -> None:
    answer = input(f"{message} [y/N]: ").strip().lower()
    if answer != "y":
        raise InfraError("Provisioning cancelled.")


def ensure_project(project_id: str) -> bool:
    project = get_project(project_id)
    if project is not None:
        lifecycle = project.get("lifecycleState")
        if lifecycle not in {"ACTIVE", None}:
            raise InfraError(
                f"Project {project_id} exists with lifecycle state {lifecycle}."
            )
        print(f"Project {project_id}: already exists.")
        return False

    confirm(f"Create Google Cloud project {project_id}?")
    run_command(
        [
            "gcloud",
            "projects",
            "create",
            project_id,
            "--name=Sabor da Terra",
        ]
    )
    print(f"Project {project_id}: created.")
    return True


def ensure_billing_account(project_id: str, billing_account_id: str) -> None:
    accounts = run_json(
        [
            "gcloud",
            "billing",
            "accounts",
            "list",
            "--filter=open=true",
            "--format=json",
        ]
    )
    available = {
        str(account.get("name", "")).split("/")[-1]
        for account in accounts
        if isinstance(account, dict)
    }
    if billing_account_id not in available:
        raise InfraError(
            "The configured billing account is unavailable or closed. "
            "Verify gcloud billing accounts list."
        )

    result = run_command(
        [
            "gcloud",
            "billing",
            "projects",
            "describe",
            project_id,
            "--format=json",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        try:
            billing = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise InfraError("gcloud returned invalid billing project data.") from error
        linked = str(billing.get("billingAccountName", "")).split("/")[-1]
        if linked:
            if linked == billing_account_id:
                print("Billing: already linked to the authorized account.")
                return
            raise InfraError(
                f"Project is linked to billing account {linked}, not the configured "
                f"{billing_account_id}. Refuse to relink automatically."
            )

    confirm(
        f"Link project {project_id} to billing account {billing_account_id}?"
    )
    run_command(
        [
            "gcloud",
            "billing",
            "projects",
            "link",
            project_id,
            "--billing-account",
            billing_account_id,
        ]
    )
    print("Billing: linked.")


def enable_required_apis(project_id: str) -> None:
    run_command(
        [
            "gcloud",
            "services",
            "enable",
            *STAGE_4_APIS,
            "--project",
            project_id,
        ]
    )
    print("Required project APIs: enabled.")


def ensure_project_budget(
    project_id: str,
    billing_account_id: str,
    amount_usd: float,
) -> None:
    display_name = f"Sabor da Terra - {project_id}"
    budgets = run_json(
        [
            "gcloud",
            "billing",
            "budgets",
            "list",
            "--billing-account",
            billing_account_id,
            "--format=json",
        ]
    )

    existing = next(
        (
            budget
            for budget in budgets
            if isinstance(budget, dict)
            and budget.get("displayName") == display_name
        ),
        None,
    )
    if existing is not None:
        print("Budget: already exists.")
        return

    confirm(
        f"Create project budget for {project_id} at US$ {amount_usd:.2f} "
        "with alerts at 50%, 80%, and 100%?"
    )
    command = [
        "gcloud",
        "billing",
        "budgets",
        "create",
        "--billing-account",
        billing_account_id,
        "--display-name",
        display_name,
        "--budget-amount",
        f"{amount_usd:.2f}USD",
        "--calendar-period",
        "month",
        "--filter-projects",
        f"projects/{project_id}",
    ]
    for threshold in (0.5, 0.8, 1.0):
        command.extend(["--threshold-rule", f"basis=current-spend,percent={threshold:.1f}"])
    run_command(command)
    print("Budget: created.")


def provision(config: dict) -> None:
    require_commands(["gcloud"])

    project_id = config["project_id"]
    billing_account_id = config["billing_account_id"]
    account = get_active_account()
    print(f"Active gcloud account: {account}")

    ensure_project(project_id)
    ensure_billing_account(project_id, billing_account_id)
    enable_required_apis(project_id)
    ensure_project_budget(
        project_id,
        billing_account_id,
        float(config["budget"]["amount_usd"]),
    )


if __name__ == "__main__":
    main_entry(
        base_parser("Provision the Sabor da Terra project and billing"),
        provision,
    )
