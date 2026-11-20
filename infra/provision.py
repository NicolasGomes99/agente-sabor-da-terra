import json
import os
import re
import secrets
import urllib.parse
from getpass import getpass
from typing import Any

from cloudsql import connection_name, run_sql_with_proxy
from common import (
    InfraError,
    base_parser,
    command_failure,
    format_command,
    is_missing_resource,
    main_entry,
    register_secret,
    require_commands,
    run_command,
)
from hosting import ensure_hosting


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

STAGE_6_APIS = [
    "sqladmin.googleapis.com",
]

STAGE_7_APIS = [
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "run.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
]

SERVICE_ACCOUNTS = {
    "api": (
        "sabor-da-terra-api",
        "Backend API and agents",
    ),
    "tasks": (
        "sabor-da-terra-tasks",
        "Cloud Tasks triage processing identity",
    ),
    "scheduler": (
        "sabor-da-terra-scheduler",
        "Cloud Scheduler entry identity",
    ),
}


def run_json(command: list[str]) -> Any:
    result = run_command(
        command,
        check=True,
        capture_output=True,
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise InfraError(
            f"Invalid JSON returned by: {format_command(command)}"
        ) from None


def describe_json(
    command: list[str],
    action: str,
) -> Any | None:
    result = run_command(
        command,
        check=False,
        capture_output=True,
    )

    if result.returncode != 0:
        if is_missing_resource(result, action):
            return None

        raise command_failure(result, action)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise InfraError(
            f"{action} returned invalid JSON."
        ) from None


def confirm(message: str) -> None:
    answer = input(
        f"{message} [y/N]: "
    ).strip().lower()

    if answer != "y":
        raise InfraError("Provisioning cancelled.")


def get_active_account() -> str:
    result = run_command(
        [
            "gcloud",
            "auth",
            "list",
            "--filter=status:ACTIVE",
            "--format=value(account)",
        ],
        capture_output=True,
    )

    accounts = result.stdout.strip().splitlines()

    if not accounts:
        raise InfraError(
            "No active gcloud account. Run gcloud auth login."
        )

    return accounts[0]


def verify_adc() -> None:
    run_command(
        [
            "gcloud",
            "auth",
            "application-default",
            "print-access-token",
        ],
        capture_output=True,
    )

    print("Application Default Credentials: available.")


def get_project(project_id: str) -> dict | None:
    return describe_json(
        [
            "gcloud",
            "projects",
            "describe",
            project_id,
            "--format=json",
        ],
        f"Project {project_id} lookup",
    )


def ensure_project(project_id: str) -> bool:
    project = get_project(project_id)

    if project is not None:
        lifecycle = project.get("lifecycleState")

        if lifecycle not in {"ACTIVE", None}:
            raise InfraError(
                f"Project {project_id} exists with "
                f"lifecycle state {lifecycle}."
            )

        print(f"Project {project_id}: already exists.")
        return False

    confirm(
        f"Create Google Cloud project {project_id}?"
    )

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


def get_billing_currency(
    billing_account_id: str,
) -> str:
    account = run_json(
        [
            "gcloud",
            "billing",
            "accounts",
            "describe",
            billing_account_id,
            "--format=json",
        ]
    )

    currency = str(
        account.get("currencyCode", "")
    ).strip().upper()

    if not currency:
        raise InfraError(
            "Could not determine billing account currency."
        )

    return currency


def ensure_billing_account(
    project_id: str,
    billing_account_id: str,
    expected_currency: str = "USD",
) -> str:
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
            "The configured billing account is unavailable or closed."
        )

    currency = get_billing_currency(
        billing_account_id
    )

    if currency != expected_currency:
        raise InfraError(
            f"Billing account uses {currency}, "
            f"but the configured budget uses {expected_currency}."
        )

    billing = describe_json(
        [
            "gcloud",
            "billing",
            "projects",
            "describe",
            project_id,
            "--format=json",
        ],
        f"Billing information for project {project_id}",
    )

    if billing is not None:
        linked = str(
            billing.get("billingAccountName", "")
        ).split("/")[-1]

        if linked:
            if linked != billing_account_id:
                raise InfraError(
                    f"Project is linked to billing account {linked}. "
                    "Refuse to relink automatically."
                )

            if billing.get("billingEnabled") is False:
                raise InfraError(
                    "The project billing account is linked "
                    "but billing is disabled."
                )

            print(
                "Billing: already linked to the authorized account."
            )

            return currency

    confirm(
        f"Link project {project_id} to billing account "
        f"{billing_account_id}?"
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

    return currency


def enable_apis(
    project_id: str,
    apis: list[str],
) -> None:
    run_command(
        [
            "gcloud",
            "services",
            "enable",
            *apis,
            "--project",
            project_id,
        ]
    )


def enable_required_apis(project_id: str) -> None:
    enable_apis(project_id, STAGE_4_APIS)

    print("Required project APIs: enabled.")


def enable_stage_5_apis(project_id: str) -> None:
    enable_apis(project_id, STAGE_5_APIS)

    print("Stage 5 APIs: enabled.")


def _budget_amount(
    amount_usd: float,
) -> tuple[int, int]:
    units = int(amount_usd)

    nanos = int(
        round(
            (amount_usd - units)
            * 1_000_000_000
        )
    )

    if nanos == 1_000_000_000:
        units += 1
        nanos = 0

    return units, nanos


def _matches_project_filter(
    budget: dict,
    project_keys: set[str],
) -> bool:
    projects = (
        (budget.get("budgetFilter") or {})
        .get("projects") or []
    )

    return (
        len(projects) == 1
        and str(projects[0]) in project_keys
    )


def verify_project_budget(
    budget: dict,
    project_keys: set[str],
    amount_usd: float,
    currency: str,
) -> list[str]:
    problems: list[str] = []

    if not _matches_project_filter(
        budget,
        project_keys,
    ):
        problems.append(
            "Budget is not restricted to the configured project."
        )

    budget_filter = budget.get("budgetFilter") or {}

    if budget_filter.get("calendarPeriod", "MONTH") != "MONTH":
        problems.append(
            "Budget must use a monthly calendar period."
        )

    if budget_filter.get("services"):
        problems.append(
            "Budget must cover all project services."
        )

    if budget_filter.get("labels"):
        problems.append(
            "Budget must not restrict resources by label."
        )

    specified = (
        (budget.get("amount") or {})
        .get("specifiedAmount") or {}
    )

    if (
        str(specified.get("currencyCode", "")).upper()
        != currency.upper()
    ):
        problems.append(
            "Budget currency does not match."
        )

    units, nanos = _budget_amount(amount_usd)

    try:
        actual_units = int(
            specified.get("units", 0) or 0
        )

        actual_nanos = int(
            specified.get("nanos", 0) or 0
        )

    except (TypeError, ValueError):
        actual_units = -1
        actual_nanos = -1

    if (
        actual_units,
        actual_nanos,
    ) != (units, nanos):
        problems.append(
            "Budget amount does not match."
        )

    thresholds = sorted(
        (
            float(rule.get("thresholdPercent", 0)),
            str(
                rule.get(
                    "spendBasis",
                    "CURRENT_SPEND",
                )
            ).upper(),
        )
        for rule in budget.get("thresholdRules") or []
        if isinstance(rule, dict)
    )

    expected_thresholds = [
        (0.5, "CURRENT_SPEND"),
        (0.8, "CURRENT_SPEND"),
        (1.0, "CURRENT_SPEND"),
    ]

    if thresholds != expected_thresholds:
        problems.append(
            "Budget alert thresholds do not match."
        )

    all_updates = budget.get("allUpdatesRule") or {}

    if all_updates.get("disableDefaultIamRecipients"):
        problems.append(
            "Default IAM budget notifications are disabled."
        )

    return problems


def ensure_project_budget(
    project_id: str,
    billing_account_id: str,
    amount_usd: float,
    currency: str,
) -> None:
    display_name = f"Sabor da Terra - {project_id}"

    project = get_project(project_id)

    project_keys = {
        f"projects/{project_id}"
    }

    if project and project.get("projectNumber"):
        project_keys.add(
            f"projects/{project['projectNumber']}"
        )

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

    matching = [
        budget
        for budget in budgets
        if isinstance(budget, dict)
        and (
            budget.get("displayName") == display_name
            or _matches_project_filter(
                budget,
                project_keys,
            )
        )
    ]

    if matching:
        problems: list[str] = []

        for budget in matching:
            problems.extend(
                verify_project_budget(
                    budget,
                    project_keys,
                    amount_usd,
                    currency,
                )
            )

        if problems:
            details = "\n".join(
                f"- {problem}"
                for problem in problems
            )

            raise InfraError(
                "An existing budget does not match "
                "the planned configuration. "
                f"It was not modified.\n{details}"
            )

        print("Budget: already exists and matches the plan.")

        return

    confirm(
        f"Create monthly budget of {currency} "
        f"{amount_usd:.2f} for {project_id}? "
        "Budget alerts do not prevent additional charges."
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
        f"{amount_usd:.2f}{currency}",
        "--calendar-period",
        "month",
        "--filter-projects",
        f"projects/{project_id}",
    ]

    for threshold in (0.5, 0.8, 1.0):
        command.extend(
            [
                "--threshold-rule",
                f"basis=current-spend,percent={threshold:.1f}",
            ]
        )

    run_command(command)

    print("Budget: created.")


def get_service_account(
    project_id: str,
    account_name: str,
) -> dict | None:
    email = (
        f"{account_name}@"
        f"{project_id}.iam.gserviceaccount.com"
    )

    return describe_json(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "describe",
            email,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Service account {email} lookup",
    )


def ensure_service_accounts(
    project_id: str,
) -> dict[str, str]:
    emails: dict[str, str] = {}

    for key, (name, description) in SERVICE_ACCOUNTS.items():
        email = (
            f"{name}@"
            f"{project_id}.iam.gserviceaccount.com"
        )

        account = get_service_account(
            project_id,
            name,
        )

        if account is None:
            run_command(
                [
                    "gcloud",
                    "iam",
                    "service-accounts",
                    "create",
                    name,
                    "--display-name",
                    description,
                    "--project",
                    project_id,
                ]
            )

            print(f"Service account {name}: created.")

        elif account.get("disabled"):
            raise InfraError(
                f"Service account {name} is disabled."
            )

        else:
            print(f"Service account {name}: already exists.")

        emails[key] = email

    return emails


def get_secret(
    project_id: str,
    secret_name: str,
) -> dict | None:
    return describe_json(
        [
            "gcloud",
            "secrets",
            "describe",
            secret_name,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Secret {secret_name} lookup",
    )


def get_enabled_secret_versions(
    project_id: str,
    secret_name: str,
) -> list[dict]:
    versions = describe_json(
        [
            "gcloud",
            "secrets",
            "versions",
            "list",
            secret_name,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Secret {secret_name} versions lookup",
    )

    if versions is None:
        return []

    return [
        version
        for version in versions
        if isinstance(version, dict)
        and version.get("state") == "ENABLED"
    ]


def get_secret_version(
    project_id: str,
    secret_name: str,
) -> str:
    versions = get_enabled_secret_versions(
        project_id,
        secret_name,
    )

    if not versions:
        raise InfraError(
            f"Secret {secret_name} has no enabled version."
        )

    try:
        version_ids = [
            int(
                version["name"].rsplit("/", 1)[-1]
            )
            for version in versions
        ]

    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        raise InfraError(
            f"Invalid version metadata for secret {secret_name}."
        ) from None

    return str(max(version_ids))


def get_secret_value(
    project_id: str,
    secret_name: str,
) -> str:
    version = get_secret_version(
        project_id,
        secret_name,
    )

    result = run_command(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            version,
            "--secret",
            secret_name,
            "--project",
            project_id,
        ],
        capture_output=True,
    )

    value = result.stdout.rstrip("\r\n")

    if not value:
        raise InfraError(
            f"Secret {secret_name} is empty."
        )

    register_secret(value)

    return value


def add_secret_version(
    project_id: str,
    secret_name: str,
    value: str,
) -> None:
    register_secret(value)

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
        secrets=[value],
        capture_output=True,
    )


def ensure_secret(
    project_id: str,
    secret_name: str,
    value: str | None = None,
) -> bool:
    existing = get_secret(
        project_id,
        secret_name,
    )

    created = False

    if existing is None:
        if not value:
            raise InfraError(
                f"Secret {secret_name} requires an initial value."
            )

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

        created = True

    elif get_enabled_secret_versions(
        project_id,
        secret_name,
    ):
        print(f"Secret {secret_name}: preserved.")

        return False

    if not value:
        raise InfraError(
            f"Secret {secret_name} has no enabled version."
        )

    add_secret_version(
        project_id,
        secret_name,
        value,
    )

    print(
        f"Secret {secret_name}: "
        f"{'created' if created else 'version restored'}."
    )

    return created


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
            "--condition=None",
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
            "--condition=None",
            "--project",
            project_id,
        ]
    )


def bind_service_account_user(
    project_id: str,
    service_account_email: str,
    member_email: str,
) -> None:
    run_command(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "add-iam-policy-binding",
            service_account_email,
            "--member",
            f"serviceAccount:{member_email}",
            "--role",
            "roles/iam.serviceAccountUser",
            "--condition=None",
            "--project",
            project_id,
        ]
    )


def configure_inference(
    project_id: str,
    config: dict,
    api_email: str,
) -> None:
    mode = config["inference"]["mode"]

    if mode == "vertex":
        enable_apis(
            project_id,
            ["aiplatform.googleapis.com"],
        )

        bind_project_role(
            project_id,
            api_email,
            "roles/aiplatform.user",
        )

        print(
            "Vertex AI: configured. "
            "Inference may generate charges."
        )

        return

    if mode != "developer":
        raise InfraError(
            "Unsupported inference mode."
        )

    enable_apis(
        project_id,
        ["generativelanguage.googleapis.com"],
    )

    existing = get_secret(
        project_id,
        "gemini-api-key",
    )

    if existing is None or not get_enabled_secret_versions(
        project_id,
        "gemini-api-key",
    ):
        key = os.getenv("GEMINI_API_KEY")

        if not key:
            key = getpass(
                "Dedicated Gemini API key (hidden): "
            ).strip()

        if not key:
            raise InfraError(
                "GEMINI_API_KEY is required for developer inference."
            )

        ensure_secret(
            project_id,
            "gemini-api-key",
            key,
        )

    else:
        print(
            "Secret gemini-api-key: preserved."
        )

    bind_secret_accessor(
        project_id,
        "gemini-api-key",
        api_email,
    )

    print(
        "Gemini Developer API: configured. "
        "Verify billing, quotas and data privacy before inference."
    )


def configure_stage_5(
    project_id: str,
    config: dict,
) -> dict[str, str]:
    enable_stage_5_apis(project_id)

    emails = ensure_service_accounts(
        project_id
    )

    api_email = emails["api"]

    ensure_secret(
        project_id,
        "jwt-secret-key",
        secrets.token_urlsafe(48),
    )

    bind_project_role(
        project_id,
        api_email,
        "roles/cloudsql.client",
    )

    bind_service_account_user(
        project_id,
        emails["tasks"],
        api_email,
    )

    bind_secret_accessor(
        project_id,
        "jwt-secret-key",
        api_email,
    )

    configure_inference(
        project_id,
        config,
        api_email,
    )

    print("Stage 5 identities and secrets: configured.")

    return emails


def get_sql_instance(
    project_id: str,
    instance_name: str,
) -> dict | None:
    return describe_json(
        [
            "gcloud",
            "sql",
            "instances",
            "describe",
            instance_name,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Cloud SQL instance {instance_name} lookup",
    )


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().upper()

    return value


def validate_sql_instance(
    instance: dict,
    config: dict,
) -> None:
    database = config["database"]
    settings = instance.get("settings") or {}
    ip = settings.get("ipConfiguration") or {}
    backups = settings.get("backupConfiguration") or {}

    mismatches: list[str] = []

    def check(
        label: str,
        actual: Any,
        expected: Any,
    ) -> None:
        if _normalized(actual) != _normalized(expected):
            mismatches.append(
                f"{label}: found {actual!r}, expected {expected!r}"
            )

    check(
        "database version",
        instance.get("databaseVersion"),
        "POSTGRES_16",
    )

    check(
        "region",
        instance.get("region"),
        config["region"],
    )

    check(
        "edition",
        settings.get("edition"),
        "ENTERPRISE",
    )

    check(
        "tier",
        settings.get("tier"),
        database["tier"],
    )

    check(
        "availability type",
        settings.get("availabilityType"),
        "ZONAL",
    )

    check(
        "disk type",
        settings.get("dataDiskType"),
        "PD_SSD",
    )

    check(
        "disk size (GB)",
        str(settings.get("dataDiskSizeGb")),
        str(database["storage_size_gb"]),
    )

    check(
        "storage auto-increase",
        settings.get("storageAutoResize"),
        False,
    )

    check(
        "backups",
        backups.get("enabled", False),
        False,
    )

    check(
        "point-in-time recovery",
        backups.get(
            "pointInTimeRecoveryEnabled",
            False,
        ),
        False,
    )

    check(
        "deletion protection",
        settings.get("deletionProtectionEnabled"),
        True,
    )

    check(
        "public IPv4",
        ip.get("ipv4Enabled"),
        True,
    )

    check(
        "authorized networks",
        len(ip.get("authorizedNetworks") or []),
        0,
    )

    check(
        "connector enforcement",
        settings.get("connectorEnforcement"),
        "REQUIRED",
    )

    check(
        "server CA mode",
        ip.get("serverCaMode"),
        "GOOGLE_MANAGED_INTERNAL_CA",
    )

    if mismatches:
        details = "\n".join(
            f"- {mismatch}"
            for mismatch in mismatches
        )

        raise InfraError(
            "Existing Cloud SQL instance does not match "
            "the planned configuration. "
            f"It was not modified.\n{details}"
        )


def ensure_sql_instance(
    project_id: str,
    config: dict,
    admin_password: str,
) -> dict:
    database = config["database"]
    name = database["instance_name"]
    region = config["region"]

    instance = get_sql_instance(
        project_id,
        name,
    )

    if instance is None:
        confirm(
            f"Create Cloud SQL PostgreSQL 16 instance "
            f"{name} in {region}? This resource is billed."
        )

        run_command(
            [
                "gcloud",
                "sql",
                "instances",
                "create",
                name,
                "--database-version=POSTGRES_16",
                "--edition=enterprise",
                f"--tier={database['tier']}",
                f"--region={region}",
                "--availability-type=zonal",
                f"--storage-size={database['storage_size_gb']}GB",
                "--storage-type=SSD",
                "--no-storage-auto-increase",
                "--no-backup",
                "--no-final-backup",
                "--no-retain-backups-on-delete",
                "--assign-ip",
                "--connector-enforcement=REQUIRED",
                "--server-ca-mode=GOOGLE_MANAGED_INTERNAL_CA",
                "--deletion-protection",
                f"--root-password={admin_password}",
                "--project",
                project_id,
            ],
            secrets=[admin_password],
            capture_output=True,
        )

        instance = get_sql_instance(
            project_id,
            name,
        )

        if instance is None:
            raise InfraError(
                "Cloud SQL instance not found after creation."
            )

    validate_sql_instance(
        instance,
        config,
    )

    print(f"Cloud SQL instance {name}: configured.")

    return instance


def ensure_sql_database(
    project_id: str,
    instance_name: str,
    database_name: str,
) -> None:
    existing = describe_json(
        [
            "gcloud",
            "sql",
            "databases",
            "describe",
            database_name,
            "--instance",
            instance_name,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Cloud SQL database {database_name} lookup",
    )

    if existing is not None:
        print(
            f"Cloud SQL database {database_name}: already exists."
        )

        return

    run_command(
        [
            "gcloud",
            "sql",
            "databases",
            "create",
            database_name,
            "--instance",
            instance_name,
            "--project",
            project_id,
        ]
    )

    print(
        f"Cloud SQL database {database_name}: created."
    )


def quote_sql_literal(value: str) -> str:
    if "\x00" in value:
        raise InfraError(
            "Invalid PostgreSQL literal."
        )

    return "'" + value.replace("'", "''") + "'"


def quote_sql_identifier(value: str) -> str:
    if not re.fullmatch(
        r"[a-z_][a-z0-9_]{0,62}",
        value,
    ):
        raise InfraError(
            "Invalid PostgreSQL identifier."
        )

    return f'"{value}"'


def build_database_url(
    project_id: str,
    region: str,
    instance_name: str,
    database_name: str,
    username: str,
    password: str,
) -> str:
    encoded_user = urllib.parse.quote(
        username,
        safe="",
    )

    encoded_password = urllib.parse.quote(
        password,
        safe="",
    )

    socket_name = connection_name(
        project_id,
        region,
        instance_name,
    )

    host = urllib.parse.quote(
        f"/cloudsql/{socket_name}",
        safe="/:",
    )

    url = (
        f"postgresql+asyncpg://"
        f"{encoded_user}:{encoded_password}@/"
        f"{database_name}?host={host}"
    )

    register_secret(password)
    register_secret(url)

    return url


def get_database_url_credentials(
    database_url: str,
) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(
        database_url
    )

    if parsed.scheme not in {
        "postgresql",
        "postgresql+asyncpg",
    }:
        raise InfraError(
            "Existing database-url is not a PostgreSQL URL."
        )

    username = urllib.parse.unquote(
        parsed.username or ""
    )

    password = urllib.parse.unquote(
        parsed.password or ""
    )

    if not username or not password:
        raise InfraError(
            "Existing database-url does not contain app credentials."
        )

    register_secret(password)

    return username, password


def build_database_setup_sql(
    database_name: str,
    admin_user: str,
    migrator_user: str,
    migrator_password: str,
    application_user: str,
    application_password: str,
) -> str:
    if len({
        admin_user,
        migrator_user,
        application_user,
    }) != 3:
        raise InfraError(
            "Database roles must be different."
        )

    database = quote_sql_identifier(database_name)
    admin = quote_sql_identifier(admin_user)
    migrator = quote_sql_identifier(migrator_user)
    application = quote_sql_identifier(application_user)

    register_secret(migrator_password)
    register_secret(application_password)

    role_statements: list[str] = []

    for username, password in (
        (migrator_user, migrator_password),
        (application_user, application_password),
    ):
        identifier = quote_sql_identifier(username)
        name_literal = quote_sql_literal(username)
        password_literal = quote_sql_literal(password)

        role_statements.append(
            f"""
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = {name_literal}
    ) THEN
        CREATE ROLE {identifier}
            LOGIN NOSUPERUSER
            NOCREATEDB NOCREATEROLE
            INHERIT
            PASSWORD {password_literal};
    ELSE
        IF EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = {name_literal}
            AND (
                rolsuper
                OR rolcreatedb
                OR rolcreaterole
                OR rolreplication
                OR rolbypassrls
            )
        ) THEN
            RAISE EXCEPTION
                'Existing database role has administrative privileges';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM pg_auth_members AS membership
            JOIN pg_roles AS member
                ON member.oid = membership.member
            WHERE member.rolname = {name_literal}
        ) THEN
            RAISE EXCEPTION
                'Existing database role has unexpected memberships';
        END IF;

        ALTER ROLE {identifier}
            LOGIN PASSWORD {password_literal};
    END IF;
"""
        )

    role_sql = "\n".join(
        role_statements
    )

    delimiter = f"$setup_{secrets.token_hex(8)}$"

    while delimiter in role_sql:
        delimiter = f"$setup_{secrets.token_hex(8)}$"

    return f"""
SET LOCAL standard_conforming_strings = on;

DO {delimiter}
BEGIN
{role_sql}
END;
{delimiter};

GRANT {migrator} TO {admin} WITH INHERIT TRUE;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON DATABASE {database} FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE {database} FROM PUBLIC;

GRANT CONNECT ON DATABASE {database}
    TO {migrator}, {application};

GRANT USAGE ON SCHEMA public
    TO {migrator}, {application};

REVOKE CREATE ON SCHEMA public FROM {application};

GRANT CREATE ON SCHEMA public
    TO {migrator};

CREATE EXTENSION IF NOT EXISTS vector;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public
    TO {application};

GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA public
    TO {application};

ALTER DEFAULT PRIVILEGES FOR ROLE {migrator}
    IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLES TO {application};

ALTER DEFAULT PRIVILEGES FOR ROLE {migrator}
    IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE
    ON SEQUENCES TO {application};
"""


def configure_stage6(
    project_id: str,
    config: dict,
) -> None:
    proxy_path = os.getenv(
        "CLOUD_SQL_PROXY_BIN",
        "cloud-sql-proxy",
    )

    require_commands(
        ["gcloud", proxy_path]
    )

    enable_apis(
        project_id,
        STAGE_6_APIS,
    )

    database = config["database"]

    instance_name = database["instance_name"]
    database_name = database["database_name"]
    admin_user = database["admin_user"]
    migrator_user = database["migrator_user"]
    application_user = database["application_user"]
    region = config["region"]

    existing_instance = get_sql_instance(
        project_id,
        instance_name,
    )

    if existing_instance is not None:
        validate_sql_instance(
            existing_instance,
            config,
        )

        if not get_enabled_secret_versions(
            project_id,
            "database-admin-password",
        ):
            raise InfraError(
                "An existing Cloud SQL instance has no enabled "
                "administrator password secret. "
                "Recover its credentials before continuing."
            )

    ensure_secret(
        project_id,
        "database-admin-password",
        secrets.token_urlsafe(48),
    )

    ensure_secret(
        project_id,
        "database-migrator-password",
        secrets.token_urlsafe(48),
    )

    admin_password = get_secret_value(
        project_id,
        "database-admin-password",
    )

    migrator_password = get_secret_value(
        project_id,
        "database-migrator-password",
    )

    ensure_sql_instance(
        project_id,
        config,
        admin_password,
    )

    ensure_sql_database(
        project_id,
        instance_name,
        database_name,
    )

    existing_secret = get_secret(
        project_id,
        "database-url",
    )

    if (
        existing_secret is not None
        and get_enabled_secret_versions(
            project_id,
            "database-url",
        )
    ):
        existing_url = get_secret_value(
            project_id,
            "database-url",
        )

        username, application_password = (
            get_database_url_credentials(
                existing_url
            )
        )

        expected_url = build_database_url(
            project_id,
            region,
            instance_name,
            database_name,
            application_user,
            application_password,
        )

        if (
            username != application_user
            or existing_url != expected_url
        ):
            raise InfraError(
                "Existing database-url does not match "
                "the configured database and application user."
            )

    else:
        application_password = (
            secrets.token_urlsafe(48)
        )

        database_url = build_database_url(
            project_id,
            region,
            instance_name,
            database_name,
            application_user,
            application_password,
        )

        ensure_secret(
            project_id,
            "database-url",
            database_url,
        )

    sql = build_database_setup_sql(
        database_name=database_name,
        admin_user=admin_user,
        migrator_user=migrator_user,
        migrator_password=migrator_password,
        application_user=application_user,
        application_password=application_password,
    )

    run_sql_with_proxy(
        project_id,
        connection_name(
            project_id,
            region,
            instance_name,
        ),
        database_name,
        admin_user,
        admin_password,
        sql,
        proxy_path=proxy_path,
    )

    api_email = (
        f"{SERVICE_ACCOUNTS['api'][0]}"
        f"@{project_id}.iam.gserviceaccount.com"
    )

    bind_secret_accessor(
        project_id,
        "database-url",
        api_email,
    )

    print(
        "Cloud SQL database, users, privileges "
        "and pgvector: configured."
    )


def get_repository_name(config: dict) -> str:
    name = config["artifacts"].get(
        "repository_name"
    )

    if not isinstance(name, str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,62}",
        name,
    ):
        raise InfraError(
            "Invalid Artifact Registry repository name."
        )

    return name


def get_bucket_name(config: dict) -> str:
    name = config["storage"].get(
        "bucket_name"
    )

    if name is None:
        name = (
            f"{config['project_id']}-documents"
        )

    if not isinstance(name, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]",
        name,
    ):
        raise InfraError(
            "Invalid Cloud Storage bucket name."
        )

    return name


def get_artifact_repository(
    project_id: str,
    region: str,
    repository_name: str,
) -> dict | None:
    return describe_json(
        [
            "gcloud",
            "artifacts",
            "repositories",
            "describe",
            repository_name,
            "--location",
            region,
            "--project",
            project_id,
            "--format=json",
        ],
        f"Artifact Registry repository {repository_name} lookup",
    )


def validate_artifact_repository(
    repository: dict,
) -> None:
    if repository.get("format") != "DOCKER":
        raise InfraError(
            "Artifact Registry repository must use Docker format."
        )

    if repository.get("mode") != "STANDARD_REPOSITORY":
        raise InfraError(
            "Artifact Registry repository must use Standard mode."
        )

    docker = repository.get("dockerConfig") or {}

    if docker.get("immutableTags"):
        raise InfraError(
            "Artifact Registry immutable tags must be disabled."
        )

    if repository.get("cleanupPolicies"):
        raise InfraError(
            "Unexpected Artifact Registry cleanup policies."
        )


def ensure_artifact_repository(
    project_id: str,
    config: dict,
) -> None:
    region = config["region"]
    name = get_repository_name(config)

    repository = get_artifact_repository(
        project_id,
        region,
        name,
    )

    if repository is None:
        confirm(
            f"Create Artifact Registry repository {name}? "
            "Storage usage may generate costs."
        )

        run_command(
            [
                "gcloud",
                "artifacts",
                "repositories",
                "create",
                name,
                "--repository-format=docker",
                "--mode=standard-repository",
                "--disable-vulnerability-scanning",
                "--location",
                region,
                "--project",
                project_id,
            ]
        )

        repository = get_artifact_repository(
            project_id,
            region,
            name,
        )

        if repository is None:
            raise InfraError(
                "Artifact Registry repository not found after creation."
            )

    validate_artifact_repository(
        repository
    )

    print(
        f"Artifact Registry repository {name}: configured."
    )


def get_storage_bucket(
    project_id: str,
    bucket_name: str,
) -> dict | None:
    return describe_json(
        [
            "gcloud",
            "storage",
            "buckets",
            "describe",
            f"gs://{bucket_name}",
            "--raw",
            "--project",
            project_id,
            "--format=json",
        ],
        f"Cloud Storage bucket {bucket_name} lookup",
    )


def validate_storage_bucket(
    bucket: dict,
    project_number: str,
    region: str,
) -> None:
    iam = bucket.get("iamConfiguration") or {}
    uniform = iam.get("uniformBucketLevelAccess") or {}
    namespace = bucket.get("hierarchicalNamespace") or {}
    versioning = bucket.get("versioning") or {}
    soft_delete = bucket.get("softDeletePolicy") or {}
    retention = bucket.get("retentionPolicy") or {}
    lifecycle = bucket.get("lifecycle") or {}
    encryption = bucket.get("encryption") or {}

    checks = {
        "project ownership": (
            str(bucket.get("projectNumber"))
            == project_number
        ),
        "region": (
            str(bucket.get("location", "")).lower()
            == region.lower()
        ),
        "storage class": (
            bucket.get("storageClass") == "STANDARD"
        ),
        "uniform bucket-level access": (
            uniform.get("enabled") is True
        ),
        "public access prevention": (
            iam.get("publicAccessPrevention")
            == "enforced"
        ),
        "flat namespace": (
            namespace.get("enabled", False) is False
        ),
        "versioning disabled": (
            versioning.get("enabled", False) is False
        ),
        "soft delete disabled": (
            str(
                soft_delete.get(
                    "retentionDurationSeconds",
                    0,
                )
            ) == "0"
        ),
        "no retention policy": not retention,
        "no lifecycle rules": not lifecycle.get("rule"),
        "Google-managed encryption": (
            not encryption.get("defaultKmsKeyName")
        ),
    }

    mismatches = [
        name
        for name, valid in checks.items()
        if not valid
    ]

    if mismatches:
        details = "\n".join(
            f"- {name}"
            for name in mismatches
        )

        raise InfraError(
            "Cloud Storage bucket does not match "
            "the planned configuration. "
            f"It was not modified.\n{details}"
        )


def ensure_storage_bucket(
    project_id: str,
    config: dict,
    api_email: str,
) -> None:
    region = config["region"]
    name = get_bucket_name(config)
    bucket_url = f"gs://{name}"

    project = get_project(project_id)

    if project is None or not project.get("projectNumber"):
        raise InfraError(
            "Could not determine Google Cloud project number."
        )

    project_number = str(
        project["projectNumber"]
    )

    bucket = get_storage_bucket(
        project_id,
        name,
    )

    if bucket is None:
        confirm(
            f"Create private Cloud Storage bucket {name}? "
            "Storage usage may generate costs."
        )

        run_command(
            [
                "gcloud",
                "storage",
                "buckets",
                "create",
                bucket_url,
                "--project",
                project_id,
                "--location",
                region,
                "--default-storage-class=STANDARD",
                "--uniform-bucket-level-access",
                "--public-access-prevention",
                "--soft-delete-duration=0",
            ]
        )

        bucket = get_storage_bucket(
            project_id,
            name,
        )

        if bucket is None:
            raise InfraError(
                "Cloud Storage bucket not found after creation."
            )

    validate_storage_bucket(
        bucket,
        project_number,
        region,
    )

    run_command(
        [
            "gcloud",
            "storage",
            "buckets",
            "add-iam-policy-binding",
            bucket_url,
            "--member",
            f"serviceAccount:{api_email}",
            "--role",
            "roles/storage.objectUser",
            "--condition=None",
            "--project",
            project_id,
        ]
    )

    print(
        f"Cloud Storage bucket {name}: configured."
    )


def configure_stage7(
    project_id: str,
    config: dict,
    emails: dict[str, str],
) -> None:
    enable_apis(
        project_id,
        STAGE_7_APIS,
    )

    ensure_artifact_repository(
        project_id,
        config,
    )

    ensure_storage_bucket(
        project_id,
        config,
        emails["api"],
    )

    ensure_hosting(
        project_id,
        confirm=confirm,
    )

    print(
        "Artifact Registry, Cloud Storage "
        "and Firebase Hosting: configured."
    )


def provision(config: dict) -> None:
    proxy_path = os.getenv(
        "CLOUD_SQL_PROXY_BIN",
        "cloud-sql-proxy",
    )

    require_commands(
        [
            "gcloud",
            "firebase",
            proxy_path,
        ]
    )

    project_id = config["project_id"]
    billing_account_id = config["billing_account_id"]

    get_repository_name(config)
    get_bucket_name(config)

    budget = config["budget"]

    currency = budget.get(
        "currency",
        "USD",
    )

    amount = float(
        budget.get(
            "amount",
            budget.get("amount_usd", 1.0),
        )
    )

    account = get_active_account()

    print(f"Active gcloud account: {account}")
    print(f"Target project: {project_id}")
    print(f"Region: {config['region']}")
    print(f"Inference: {config['inference']['mode']}")
    print(f"Budget: {currency} {amount:.2f}")

    confirm(
        "Provision resources in this dedicated project? "
        "Cloud resources may generate charges."
    )

    verify_adc()

    ensure_project(
        project_id
    )

    currency = ensure_billing_account(
        project_id,
        billing_account_id,
        expected_currency=currency,
    )

    enable_required_apis(
        project_id
    )

    ensure_project_budget(
        project_id,
        billing_account_id,
        amount,
        currency,
    )

    emails = configure_stage_5(
        project_id,
        config,
    )

    configure_stage6(
        project_id,
        config,
    )

    configure_stage7(
        project_id,
        config,
        emails,
    )

    print("\nProvisioning completed successfully.")
    print(f"Project: {project_id}")
    print(f"Region: {config['region']}")
    print(f"Bucket: {get_bucket_name(config)}")
    print(f"Repository: {get_repository_name(config)}")
    print("Next step: application deployment.")


if __name__ == "__main__":
    main_entry(
        base_parser(
            "Provision the Sabor da Terra cloud environment"
        ),
        provision,
    )