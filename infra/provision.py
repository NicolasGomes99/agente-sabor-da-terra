import json
import os
import secrets
import socket
import subprocess
import time
import urllib.parse
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
    return value.rstrip("\r\n")


def get_sql_instance(project_id: str, instance_name: str) -> dict | None:
    result = run_command(
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
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InfraError("gcloud returned invalid Cloud SQL instance data.") from error


def validate_sql_instance(instance: dict, config: dict) -> None:
    database_config = config["database"]
    region = config["region"]

    settings = instance.get("settings", {})
    actual = {
        "databaseVersion": instance.get("databaseVersion"),
        "region": instance.get("region"),
        "edition": settings.get("edition"),
        "tier": settings.get("tier"),
        "availabilityType": settings.get("availabilityType"),
        "dataDiskType": settings.get("dataDiskSize"),
    }
    if actual["databaseVersion"] not in {"POSTGRES_16", None}:
        raise InfraError(
            f"Existing Cloud SQL instance uses {actual['databaseVersion']}; "
            "PostgreSQL 16 is required."
        )
    if actual["region"] not in {region, None}:
        raise InfraError(
            f"Existing Cloud SQL instance is in {actual['region']}; "
            f"{region} is required."
        )
    if actual["tier"] not in {database_config["tier"], None}:
        raise InfraError(
            f"Existing Cloud SQL tier is {actual['tier']}; "
            f"{database_config['tier']} is required."
        )


def ensure_sql_instance(project_id: str, config: dict) -> dict:
    database_config = config["database"]
    instance_name = database_config["instance_name"]
    region = config["region"]
    instance = get_sql_instance(project_id, instance_name)

    if instance is None:
        admin_password = get_secret_value(project_id, "database-admin-password")
        confirm(
            f"Create Cloud SQL PostgreSQL 16 instance {instance_name} "
            f"in {region}? This resource is billed."
        )
        run_command(
            [
                "gcloud",
                "sql",
                "instances",
                "create",
                instance_name,
                "--database-version=POSTGRES_16",
                "--edition=Enterprise",
                f"--tier={database_config['tier']}",
                f"--region={region}",
                "--availability-type=zonal",
                f"--storage-size={database_config['storage_size_gb']}GB",
                "--storage-type=SSD",
                "--no-storage-auto-increase",
                "--no-backup",
                "--assign-ip",
                "--connector-enforcement=REQUIRED",
                "--server-ca-mode=GOOGLE_MANAGED_INTERNAL_CA",
                "--deletion-protection",
                f"--root-password={admin_password}",
                "--project",
                project_id,
            ]
        )
        print(f"Cloud SQL instance {instance_name}: created.")
        instance = get_sql_instance(project_id, instance_name)
        if instance is None:
            raise InfraError("Cloud SQL instance was not found after creation.")
    else:
        print(f"Cloud SQL instance {instance_name}: already exists.")

    validate_sql_instance(instance, config)
    run_command(
        [
            "gcloud",
            "sql",
            "instances",
            "patch",
            instance_name,
            "--no-storage-auto-increase",
            "--no-backup",
            "--assign-ip",
            "--connector-enforcement=REQUIRED",
            "--server-ca-mode=GOOGLE_MANAGED_INTERNAL_CA",
            "--clear-authorized-networks",
            "--deletion-protection",
            "--project",
            project_id,
        ]
    )
    return instance


def ensure_sql_database(project_id: str, instance_name: str, database_name: str) -> None:
    result = run_command(
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
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
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


def wait_for_tcp_port(host: str, port: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise InfraError("Cloud SQL Auth Proxy did not accept connections.")


def run_sql_with_proxy(
    project_id: str,
    instance_name: str,
    region: str,
    database_name: str,
    admin_password: str,
    sql: str,
) -> None:
    proxy_path = "cloud-sql-proxy"
    port = 5434
    process = subprocess.Popen(
        [
            proxy_path,
            f"--address=127.0.0.1",
            f"--port={port}",
            f"{project_id}:{region}:{instance_name}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_tcp_port("127.0.0.1", port)
        env = os.environ.copy()
        env["PGPASSWORD"] = admin_password
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "postgres",
                "-d",
                database_name,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                "-",
            ],
            input=sql,
            env=env,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "PostgreSQL returned an unknown error."
            raise InfraError(f"Cloud SQL configuration failed: {message}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


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
    require_commands(["gcloud", "cloud-sql-proxy", "psql"])

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

    ensure_sql_instance(project_id, config)
    ensure_sql_database(project_id, instance_name, database_name)

    if get_secret(project_id, "database-admin-password") is None:
        ensure_secret(
            project_id,
            "database-admin-password",
            secrets.token_urlsafe(48),
        )
    if get_secret(project_id, "database-migrator-password") is None:
        ensure_secret(
            project_id,
            "database-migrator-password",
            secrets.token_urlsafe(48),
        )

    admin_password = get_secret_value(project_id, "database-admin-password")
    migrator_password = get_secret_value(project_id, "database-migrator-password")

    existing_database_url = get_secret(project_id, "database-url")
    if existing_database_url is not None:
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

    migrator_username = database_config["migrator_user"]

    run_command(
        [
            "gcloud",
            "sql",
            "users",
            "set-password",
            "postgres",
            "--instance",
            instance_name,
            f"--password={admin_password}",
            "--project",
            project_id,
        ]
    )

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
            || ' LOGIN PASSWORD ' || quote_literal({migrator_password_literal});
    ELSE
        EXECUTE 'ALTER ROLE ' || quote_ident({migrator_name_literal})
            || ' LOGIN PASSWORD ' || quote_literal({migrator_password_literal});
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {app_name_literal}) THEN
        EXECUTE 'CREATE ROLE ' || quote_ident({app_name_literal})
            || ' LOGIN PASSWORD ' || quote_literal({app_password_literal});
    ELSE
        EXECUTE 'ALTER ROLE ' || quote_ident({app_name_literal})
            || ' LOGIN PASSWORD ' || quote_literal({app_password_literal});
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
        instance_name,
        region,
        database_name,
        admin_password,
        sql,
    )
    print("Cloud SQL database, users, privileges and pgvector: configured.")


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
    configure_stage6(project_id, config)


if __name__ == "__main__":
    main_entry(
        base_parser("Provision the Sabor da Terra project and billing"),
        provision,
    )
