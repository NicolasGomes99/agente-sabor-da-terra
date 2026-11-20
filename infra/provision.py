import json
import os
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
            f"Google Cloud returned invalid JSON for: {format_command(command)}"
        ) from error


def describe_json(command: list[str], action: str) -> Any | None:
    """Run a describe/list command, distinguishing absence from real failures."""
    result = run_command(command, check=False, capture_output=True)
    if result.returncode != 0:
        if is_missing_resource(result, action):
            return None
        raise command_failure(result, action)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InfraError(f"{action} returned invalid JSON.") from error


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


def get_billing_currency(billing_account_id: str) -> str:
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
    currency = str(account.get("currencyCode", "")).strip() if isinstance(account, dict) else ""
    if not currency:
        raise InfraError(
            f"Could not determine the currency of billing account {billing_account_id}."
        )
    return currency


def ensure_billing_account(
    project_id: str,
    billing_account_id: str,
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
            "The configured billing account is unavailable or closed. "
            "Verify gcloud billing accounts list."
        )

    currency = get_billing_currency(billing_account_id)
    if currency != "USD":
        raise InfraError(
            f"Billing account {billing_account_id} uses {currency}. "
            "budget.amount_usd requires a USD billing account."
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
        linked = str(billing.get("billingAccountName", "")).split("/")[-1]
        if linked:
            if linked == billing_account_id:
                print("Billing: already linked to the authorized account.")
                return currency
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
    return currency


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
    email = f"{account_name}@{project_id}.iam.gserviceaccount.com"
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


def get_enabled_secret_versions(project_id: str, secret_name: str) -> list[dict]:
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
        if isinstance(version, dict) and version.get("state") == "ENABLED"
    ]


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
    )


def ensure_secret(
    project_id: str,
    secret_name: str,
    value: str | None = None,
) -> bool:
    """Create a secret when absent and make sure it has an enabled version.

    Existing credentials are preserved. A secret that exists without an enabled
    version is repaired with the supplied value instead of being deleted.
    """
    secret = get_secret(project_id, secret_name)
    created = False
    if secret is None:
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

    if value is None:
        if created:
            raise InfraError(
                f"Secret {secret_name} was created without a value. "
                "Provide a value so it can be used."
            )
        if not get_enabled_secret_versions(project_id, secret_name):
            raise InfraError(
                f"Secret {secret_name} has no enabled version. "
                "Set its value before continuing."
            )
        print(f"Secret {secret_name}: preserved.")
        return False

    if not created and get_enabled_secret_versions(project_id, secret_name):
        print(f"Secret {secret_name}: preserved.")
        return False

    add_secret_version(project_id, secret_name, value)
    if created:
        print(f"Secret {secret_name}: created.")
    else:
        print(f"Secret {secret_name}: version restored.")
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


def bind_service_account_user(
    project_id: str,
    service_account_email: str,
    member_email: str,
) -> None:
    """Allow member_email to act only as the given service account."""
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
            "--project",
            project_id,
        ]
    )


def configure_stage_5(project_id: str, config: dict) -> dict[str, str]:
    enable_stage_5_apis(project_id)
    emails = ensure_service_accounts(project_id)
    api_email = emails["api"]

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
    ensure_secret(project_id, "jwt-secret-key", secrets.token_urlsafe(48))

    bind_project_role(project_id, api_email, "roles/cloudsql.client")
    # Cloud Tasks queue-level enqueuer is granted when the queue is created (#39).
    # serviceAccountUser is limited to the triage identity used by that queue.
    bind_service_account_user(project_id, emails["tasks"], api_email)

    if config["inference"]["mode"] == "vertex":
        bind_project_role(project_id, api_email, "roles/aiplatform.user")
    else:
        if get_secret(project_id, "gemini-api-key") is None:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                gemini_key = getpass("Gemini Developer API key (input hidden): ").strip()
            if not gemini_key:
                raise InfraError("GEMINI_API_KEY is required for developer inference.")
            ensure_secret(project_id, "gemini-api-key", gemini_key)
        else:
            print("Secret gemini-api-key: preserved.")
        bind_secret_accessor(project_id, "gemini-api-key", api_email)

    for secret_name in ("database-url", "jwt-secret-key"):
        bind_secret_accessor(project_id, secret_name, api_email)

    print("Stage 5 identities and secrets: configured.")
    return emails


def get_secret_value(project_id: str, secret_name: str) -> str:
    result = run_command(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret",
            secret_name,
            "--project",
            project_id,
        ],
        check=True,
        capture_output=True,
    )
    value = result.stdout
    if not value:
        raise InfraError(f"Secret {secret_name} is empty.")
    register_secret(value.rstrip("\r\n"))
    return value.rstrip("\r\n")


def get_sql_instance(project_id: str, instance_name: str) -> dict | None:
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


def validate_sql_instance(instance: dict, config: dict) -> None:
    """Refuse to continue when an existing instance differs from the plan."""
    database_config = config["database"]
    region = config["region"]
    settings = instance.get("settings") or {}
    ip_configuration = settings.get("ipConfiguration") or {}
    backup_configuration = settings.get("backupConfiguration") or {}

    mismatches: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if _normalized(actual) != _normalized(expected):
            mismatches.append(
                f"{label}: found {actual!r}, expected {expected!r}"
            )

    check("database version", instance.get("databaseVersion"), "POSTGRES_16")
    check("region", instance.get("region"), region)
    check("edition", settings.get("edition"), "ENTERPRISE")
    check("tier", settings.get("tier"), database_config["tier"])
    if settings.get("availabilityType") is not None:
        check("availability type", settings.get("availabilityType"), "ZONAL")
    check("disk type", settings.get("dataDiskType"), "PD_SSD")
    check(
        "disk size (GB)",
        settings.get("dataDiskSizeGb"),
        database_config["storage_size_gb"],
    )
    check("storage auto-increase", settings.get("storageAutoResize"), False)
    check("backups", backup_configuration.get("enabled"), False)
    check(
        "point-in-time recovery",
        backup_configuration.get("pointInTimeRecoveryEnabled"),
        False,
    )
    check(
        "deletion protection",
        settings.get("deletionProtectionEnabled"),
        True,
    )
    check("public IPv4", ip_configuration.get("ipv4Enabled"), True)
    check(
        "authorized networks",
        len(ip_configuration.get("authorizedNetworks") or []),
        0,
    )
    check(
        "connector enforcement",
        settings.get("connectorEnforcement"),
        "REQUIRED",
    )
    check(
        "server CA mode",
        ip_configuration.get("serverCaMode"),
        "GOOGLE_MANAGED_INTERNAL_CA",
    )

    if mismatches:
        details = "\n".join(f"- {mismatch}" for mismatch in mismatches)
        raise InfraError(
            f"Existing Cloud SQL instance {database_config['instance_name']} does "
            "not match the planned configuration. It was not modified.\n"
            f"{details}"
        )


def ensure_sql_instance(
    project_id: str,
    config: dict,
    admin_password: str,
) -> dict:
    database_config = config["database"]
    instance_name = database_config["instance_name"]
    region = config["region"]
    instance = get_sql_instance(project_id, instance_name)

    if instance is None:
        confirm(
            f"Create Cloud SQL PostgreSQL 16 instance {instance_name} "
            f"in {region}? This resource is billed."
        )
        command = [
            "gcloud",
            "sql",
            "instances",
            "create",
            instance_name,
            "--database-version=POSTGRES_16",
            "--edition=enterprise",
            f"--tier={database_config['tier']}",
            f"--region={region}",
            "--availability-type=zonal",
            f"--storage-size={database_config['storage_size_gb']}GB",
            "--storage-type=SSD",
            "--no-storage-auto-increase",
            "--no-backup",
            "--no-enable-point-in-time-recovery",
            "--assign-ip",
            "--connector-enforcement=REQUIRED",
            "--server-ca-mode=GOOGLE_MANAGED_INTERNAL_CA",
            "--deletion-protection",
            f"--root-password={admin_password}",
            "--project",
            project_id,
        ]
        run_command(command, secrets=[admin_password])
        print(f"Cloud SQL instance {instance_name}: created.")
        instance = get_sql_instance(project_id, instance_name)
        if instance is None:
            raise InfraError("Cloud SQL instance was not found after creation.")
    else:
        print(f"Cloud SQL instance {instance_name}: already exists.")

    validate_sql_instance(instance, config)
    return instance


def ensure_sql_database(project_id: str, instance_name: str, database_name: str) -> None:
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
        print(f"Cloud SQL database {database_name}: already exists.")
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
    print(f"Cloud SQL database {database_name}: created.")


def quote_sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_sql_identifier(value: str) -> str:
    if not value or not all(char.isalnum() or char == "_" for char in value):
        raise InfraError("Invalid PostgreSQL identifier.")
    return '"' + value + '"'


def build_database_url(
    project_id: str,
    region: str,
    instance_name: str,
    database_name: str,
    username: str,
    password: str,
) -> str:
    encoded_user = urllib.parse.quote(username, safe="")
    encoded_password = urllib.parse.quote(password, safe="")
    socket_name = f"{project_id}:{region}:{instance_name}"
    host = urllib.parse.quote(f"/cloudsql/{socket_name}", safe="/:")
    return (
        f"postgresql+asyncpg://{encoded_user}:{encoded_password}@/"
        f"{database_name}?host={host}"
    )


def get_database_url_credentials(database_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        raise InfraError("Existing database-url is not a PostgreSQL URL.")
    username = urllib.parse.unquote(parsed.username or "")
    password = urllib.parse.unquote(parsed.password or "")
    if not username or not password:
        raise InfraError("Existing database-url does not contain app credentials.")
    return username, password


def configure_stage6(project_id: str, config: dict) -> None:
    proxy_path = os.getenv("CLOUD_SQL_PROXY_BIN", "cloud-sql-proxy")
    psql_path = os.getenv("PSQL_BIN", "psql")
    require_commands(["gcloud", proxy_path, psql_path])

    run_command(
        [
            "gcloud",
            "services",
            "enable",
            *STAGE_6_APIS,
            "--project",
            project_id,
        ]
    )

    database_config = config["database"]
    instance_name = database_config["instance_name"]
    database_name = database_config["database_name"]
    region = config["region"]

    # Secrets must have an enabled version before the instance is created or
    # any credential is read. Existing values are never rotated.
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

    admin_password = get_secret_value(project_id, "database-admin-password")
    migrator_password = get_secret_value(project_id, "database-migrator-password")

    ensure_sql_instance(project_id, config, admin_password)
    ensure_sql_database(project_id, instance_name, database_name)

    existing_database_url = get_secret(project_id, "database-url")
    if existing_database_url is not None and get_enabled_secret_versions(
        project_id, "database-url"
    ):
        existing_url_value = get_secret_value(project_id, "database-url")
        app_username, app_password = get_database_url_credentials(existing_url_value)
    else:
        app_username = database_config["application_user"]
        app_password = secrets.token_urlsafe(48)
        app_database_url = build_database_url(
            project_id,
            region,
            instance_name,
            database_name,
            app_username,
            app_password,
        )
        ensure_secret(project_id, "database-url", app_database_url)

    register_secret(app_password)
    migrator_username = database_config["migrator_user"]

    migrator_name_literal = quote_sql_literal(migrator_username)
    app_name_literal = quote_sql_literal(app_username)
    migrator_password_literal = quote_sql_literal(migrator_password)
    app_password_literal = quote_sql_literal(app_password)
    database_identifier = quote_sql_identifier(database_name)
    migrator_identifier = quote_sql_identifier(migrator_username)
    app_identifier = quote_sql_identifier(app_username)

    sql = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {migrator_name_literal}) THEN
        EXECUTE 'CREATE ROLE ' || quote_ident({migrator_name_literal})
            || ' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD '
            || quote_literal({migrator_password_literal});
    ELSE
        EXECUTE 'ALTER ROLE ' || quote_ident({migrator_name_literal})
            || ' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD '
            || quote_literal({migrator_password_literal});
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {app_name_literal}) THEN
        EXECUTE 'CREATE ROLE ' || quote_ident({app_name_literal})
            || ' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD '
            || quote_literal({app_password_literal});
    ELSE
        EXECUTE 'ALTER ROLE ' || quote_ident({app_name_literal})
            || ' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD '
            || quote_literal({app_password_literal});
    END IF;
END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE {database_identifier} TO {migrator_identifier}, {app_identifier};
GRANT USAGE ON SCHEMA public TO {migrator_identifier}, {app_identifier};
GRANT CREATE ON SCHEMA public TO {migrator_identifier};

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_identifier};
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {app_identifier};

ALTER DEFAULT PRIVILEGES FOR ROLE {migrator_identifier}
    IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_identifier};
ALTER DEFAULT PRIVILEGES FOR ROLE {migrator_identifier}
    IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {app_identifier};

CREATE EXTENSION IF NOT EXISTS vector;
"""

    run_sql_with_proxy(
        project_id,
        connection_name(project_id, region, instance_name),
        database_name,
        database_config["admin_user"],
        admin_password,
        sql,
        proxy_path=proxy_path,
        psql_path=psql_path,
    )
    print("Cloud SQL database, users, privileges and pgvector: configured.")


def _budget_amount(amount_usd: float) -> tuple[int, int]:
    units = int(amount_usd)
    nanos = int(round((amount_usd - units) * 1_000_000_000))
    if nanos == 1_000_000_000:
        units += 1
        nanos = 0
    return units, nanos


def _matches_project_filter(budget: dict, project_keys: set[str]) -> bool:
    projects = (budget.get("budgetFilter") or {}).get("projects") or []
    return any(str(project) in project_keys for project in projects)


def verify_project_budget(
    budget: dict,
    project_keys: set[str],
    amount_usd: float,
    currency: str,
) -> list[str]:
    problems: list[str] = []
    if not _matches_project_filter(budget, project_keys):
        projects = (budget.get("budgetFilter") or {}).get("projects") or []
        problems.append(
            f"filter projects are {projects!r}, expected one of {sorted(project_keys)!r}"
        )

    specified = (budget.get("amount") or {}).get("specifiedAmount") or {}
    if str(specified.get("currencyCode", "")).upper() != currency.upper():
        problems.append(
            f"currency is {specified.get('currencyCode')!r}, expected {currency!r}"
        )
    units, nanos = _budget_amount(amount_usd)
    try:
        actual_units = int(specified.get("units", 0) or 0)
        actual_nanos = int(specified.get("nanos", 0) or 0)
    except (TypeError, ValueError):
        actual_units, actual_nanos = -1, -1
    if (actual_units, actual_nanos) != (units, nanos):
        problems.append(
            f"amount is {actual_units}.{actual_nanos:09d}, "
            f"expected {units}.{nanos:09d}"
        )

    actual_thresholds = sorted(
        (
            float(rule.get("thresholdPercent", 0)),
            str(rule.get("spendBasis", "CURRENT_SPEND")).upper(),
        )
        for rule in budget.get("thresholdRules") or []
        if isinstance(rule, dict)
    )
    expected_thresholds = [(0.5, "CURRENT_SPEND"), (0.8, "CURRENT_SPEND"), (1.0, "CURRENT_SPEND")]
    if actual_thresholds != expected_thresholds:
        problems.append(
            f"thresholds are {actual_thresholds!r}, expected {expected_thresholds!r}"
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
    project_keys = {f"projects/{project_id}"}
    if project is not None and project.get("projectNumber"):
        project_keys.add(f"projects/{project['projectNumber']}")

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
            or _matches_project_filter(budget, project_keys)
        )
    ]

    if matching:
        problems: list[str] = []
        for budget in matching:
            budget_problems = verify_project_budget(
                budget,
                project_keys,
                amount_usd,
                currency,
            )
            problems.extend(
                f"{budget.get('displayName') or budget.get('name')}: {problem}"
                for problem in budget_problems
            )
        if problems:
            details = "\n".join(f"- {problem}" for problem in problems)
            raise InfraError(
                "An existing budget for this project does not match the planned "
                f"configuration. It was not modified.\n{details}"
            )
        print("Budget: already exists and matches the plan.")
        return

    confirm(
        f"Create project budget for {project_id} at {currency} {amount_usd:.2f} "
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
        f"{amount_usd:.2f}{currency}",
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
    currency = ensure_billing_account(project_id, billing_account_id)
    enable_required_apis(project_id)
    ensure_project_budget(
        project_id,
        billing_account_id,
        float(config["budget"]["amount_usd"]),
        currency,
    )
    configure_stage_5(project_id, config)
    configure_stage6(project_id, config)


if __name__ == "__main__":
    main_entry(
        base_parser("Provision the Sabor da Terra project and billing"),
        provision,
    )
