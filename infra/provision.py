import json
import os
import secrets
from getpass import getpass
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

STAGE_5_APIS = [
    "secretmanager.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com",
]

SERVICE_ACCOUNTS = {
    "api": ("sabor-da-terra-api", "Backend API and agents"),
    "tasks": ("sabor-da-terra-tasks", "Cloud Tasks triage processing identity"),
    "scheduler": ("sabor-da-terra-scheduler", "Cloud Scheduler entry identity"),
}


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


def enable_stage_5_apis(project_id: str) -> None:
    run_command(
        [
            "gcloud",
            "services",
            "enable",
            *STAGE_5_APIS,
            "--project",
            project_id,
        ]
    )
    print("Stage 5 APIs: enabled.")


def get_service_account(project_id: str, account_name: str) -> dict | None:
    result = run_command(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "describe",
            f"{account_name}@{project_id}.iam.gserviceaccount.com",
            "--project",
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
        raise InfraError("gcloud returned invalid service account data.") from error


def ensure_service_accounts(project_id: str) -> dict[str, str]:
    emails: dict[str, str] = {}
    for key, (account_name, description) in SERVICE_ACCOUNTS.items():
        email = f"{account_name}@{project_id}.iam.gserviceaccount.com"
        account = get_service_account(project_id, account_name)
        if account is not None:
            print(f"Service account {account_name}: already exists.")
        else:
            run_command(
                [
                    "gcloud",
                    "iam",
                    "service-accounts",
                    "create",
                    account_name,
                    "--display-name",
                    description,
                    "--project",
                    project_id,
                ]
            )
            print(f"Service account {account_name}: created.")
        emails[key] = email
    return emails


def get_secret(project_id: str, secret_name: str) -> dict | None:
    result = run_command(
        [
            "gcloud",
            "secrets",
            "describe",
            secret_name,
            "--project",
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
        raise InfraError("gcloud returned invalid secret data.") from error


def ensure_secret(
    project_id: str,
    secret_name: str,
    value: str | None = None,
) -> bool:
    secret = get_secret(project_id, secret_name)
    if secret is not None:
        print(f"Secret {secret_name}: preserved.")
        return False

    run_command(
        [
            "gcloud",
            "secrets",
            "create",
            secret_name,
            "--replication-policy",
            "automatic",
            "--project",
            project_id,
        ]
    )
    if value is not None:
        run_command(
            [
                "gcloud",
                "secrets",
                "versions",
                "add",
                secret_name,
                "--data-file=-",
                "--project",
                project_id,
            ],
            input_text=value,
        )
    print(f"Secret {secret_name}: created.")
    return True


def bind_project_role(
    project_id: str,
    member_email: str,
    role: str,
) -> None:
    run_command(
        [
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            project_id,
            "--member",
            f"serviceAccount:{member_email}",
            "--role",
            role,
        ]
    )


def bind_secret_accessor(
    project_id: str,
    secret_name: str,
    member_email: str,
) -> None:
    run_command(
        [
            "gcloud",
            "secrets",
            "add-iam-policy-binding",
            secret_name,
            "--member",
            f"serviceAccount:{member_email}",
            "--role",
            "roles/secretmanager.secretAccessor",
            "--project",
            project_id,
        ]
    )


def configure_stage_5(project_id: str, config: dict) -> dict[str, str]:
    enable_stage_5_apis(project_id)
    emails = ensure_service_accounts(project_id)
    api_email = emails["api"]

    ensure_secret(project_id, "database-url")
    ensure_secret(project_id, "database-admin-password", secrets.token_urlsafe(48))
    ensure_secret(project_id, "database-migrator-password", secrets.token_urlsafe(48))
    ensure_secret(project_id, "jwt-secret-key", secrets.token_urlsafe(48))

    bind_project_role(project_id, api_email, "roles/cloudsql.client")
    bind_project_role(project_id, api_email, "roles/cloudtasks.enqueuer")
    bind_project_role(
        project_id,
        api_email,
        "roles/iam.serviceAccountUser",
    )

    if config["inference"]["mode"] == "vertex":
        bind_project_role(project_id, api_email, "roles/aiplatform.user")
    else:
        existing_gemini_secret = get_secret(project_id, "gemini-api-key")
        if existing_gemini_secret is not None:
            print("Secret gemini-api-key: preserved.")
        else:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                gemini_key = getpass("Gemini Developer API key (input hidden): ").strip()
            if not gemini_key:
                raise InfraError("GEMINI_API_KEY is required for developer inference.")
            ensure_secret(project_id, "gemini-api-key", gemini_key)
        bind_secret_accessor(project_id, "gemini-api-key", api_email)

    for secret_name in ("database-url", "jwt-secret-key"):
        bind_secret_accessor(project_id, secret_name, api_email)

    print("Stage 5 identities and secrets: configured.")
    return emails


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
    configure_stage_5(project_id, config)


if __name__ == "__main__":
    main_entry(
        base_parser("Provision the Sabor da Terra project and billing"),
        provision,
    )
