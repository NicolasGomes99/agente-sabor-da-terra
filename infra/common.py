import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILENAME = "config.local.json"
DEFAULT_CONFIG = (
    REPOSITORY_ROOT / "infra" / "config.example.json"
)

_SENSITIVE_FLAG_PARTS = (
    "password",
    "passwd",
    "token",
    "credential",
    "api-key",
    "apikey",
    "secret-key",
    "client-secret",
)

_SAFE_SECRET_FLAGS = {
    "secret",
    "secret-name",
    "secret-id",
    "secrets",
}

_REGISTERED_SECRETS: set[str] = set()

_DATABASE_URL_CREDENTIALS = re.compile(
    r"(?P<prefix>[A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]+:)"
    r"(?P<secret>[^@\s]+)(?P<suffix>@)"
)

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|"
    r"api[_-]?key|credential)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)

_PERMISSION_PATTERNS = (
    r"\bpermission_denied\b",
    r"\bpermission denied\b",
    r"does not have permission",
    r"caller does not have",
    r"\bforbidden\b",
    r"\bunauthenticated\b",
    r"authentication failed",
    r"could not load the default credentials",
    r"access denied",
    r"\b40[13]\b",
)

_NOT_FOUND_PATTERNS = (
    r"\bnot_found\b",
    r"\bnot found\b",
    r"does not exist",
    r"no such",
    r"\b404\b",
    r"unknown service account",
    r"unknown project",
    r"unknown instance",
)


class InfraError(RuntimeError):
    pass


def load_config(
    path: Path | None = None,
) -> dict[str, Any]:
    config_path = (
        path
        or REPOSITORY_ROOT / "infra" / CONFIG_FILENAME
    )

    if not config_path.is_file():
        raise InfraError(
            f"Configuration file not found: {config_path}. "
            f"Copy {DEFAULT_CONFIG} and configure the environment."
        )

    try:
        config = json.loads(
            config_path.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError as error:
        raise InfraError(
            f"Invalid JSON in {config_path}: {error}"
        ) from None

    except OSError as error:
        raise InfraError(
            f"Could not read configuration: {error}"
        ) from None

    if not isinstance(config, dict):
        raise InfraError(
            "Configuration must be a JSON object."
        )

    validate_config(config)

    return config


def validate_config(
    config: dict[str, Any],
) -> None:
    required_sections = {
        "project_id": str,
        "billing_account_id": str,
        "region": str,
        "database": dict,
        "artifacts": dict,
        "storage": dict,
        "cloud_run": dict,
        "inference": dict,
        "budget": dict,
    }

    for name, expected_type in required_sections.items():
        value = config.get(name)

        if not isinstance(value, expected_type):
            raise InfraError(
                f"Configuration '{name}' must be "
                f"{expected_type.__name__}."
            )

    project_id = config["project_id"]

    if not project_id or project_id == "sabor-da-terra":
        raise InfraError(
            "Set a unique project_id in the local configuration."
        )

    if not re.fullmatch(
        r"[a-z][a-z0-9-]{4,28}[a-z0-9]",
        project_id,
    ):
        raise InfraError(
            "project_id is not a valid Google Cloud Project ID."
        )

    if config["region"] != "us-central1":
        raise InfraError(
            "Only the planned region us-central1 is supported."
        )

    billing_account_id = config["billing_account_id"]

    if not re.fullmatch(
        r"[A-Fa-f0-9]{6}-[A-Fa-f0-9]{6}-[A-Fa-f0-9]{6}",
        billing_account_id,
    ):
        raise InfraError(
            "Set a valid billing_account_id "
            "in the local configuration."
        )

    validate_database_config(
        config["database"]
    )

    validate_artifacts_config(
        config["artifacts"]
    )

    validate_storage_config(
        config["storage"]
    )

    validate_cloud_run_config(
        config["cloud_run"]
    )

    validate_inference_config(
        config["inference"]
    )

    validate_budget_config(
        config["budget"]
    )


def validate_database_config(
    database: dict[str, Any],
) -> None:
    required = {
        "instance_name": str,
        "database_name": str,
        "tier": str,
        "storage_size_gb": int,
        "backup_enabled": bool,
        "deletion_protection": bool,
        "admin_user": str,
        "migrator_user": str,
        "application_user": str,
    }

    for name, expected_type in required.items():
        value = database.get(name)

        if (
            type(value) is not expected_type
            or (
                isinstance(value, str)
                and not value.strip()
            )
        ):
            raise InfraError(
                f"Configuration 'database.{name}' must "
                f"be a non-empty {expected_type.__name__}."
            )

    instance_name = database["instance_name"]

    if not re.fullmatch(
        r"[a-z][a-z0-9-]{0,96}",
        instance_name,
    ):
        raise InfraError(
            "database.instance_name must be "
            "a valid Cloud SQL instance name."
        )

    for name in (
        "database_name",
        "migrator_user",
        "application_user",
    ):
        value = database[name]

        if not re.fullmatch(
            r"[a-z_][a-z0-9_]{0,62}",
            value,
        ):
            raise InfraError(
                f"database.{name} must be a valid "
                "PostgreSQL identifier with at most "
                "63 characters."
            )

    if database["admin_user"] != "postgres":
        raise InfraError(
            "database.admin_user must be 'postgres'."
        )

    users = {
        database["admin_user"],
        database["migrator_user"],
        database["application_user"],
    }

    if len(users) != 3:
        raise InfraError(
            "The administrator, migrator and application "
            "users must be different."
        )

    for name in (
        database["migrator_user"],
        database["application_user"],
    ):
        if name.startswith(
            ("pg_", "cloudsql")
        ):
            raise InfraError(
                "Database roles must not use reserved prefixes."
            )

    if database["database_name"] in {
        "postgres",
        "template0",
        "template1",
    }:
        raise InfraError(
            "The application must use a dedicated database."
        )

    if database["storage_size_gb"] < 10:
        raise InfraError(
            "database.storage_size_gb must be at least 10."
        )

    if database["backup_enabled"]:
        raise InfraError(
            "database.backup_enabled must be false "
            "for the planned environment."
        )

    if not database["deletion_protection"]:
        raise InfraError(
            "database.deletion_protection must be true "
            "for the planned environment."
        )

    if database["tier"] != "db-f1-micro":
        raise InfraError(
            "database.tier must be db-f1-micro "
            "for the planned environment."
        )


def validate_artifacts_config(
    artifacts: dict[str, Any],
) -> None:
    name = artifacts.get(
        "repository_name"
    )

    if (
        not isinstance(name, str)
        or not re.fullmatch(
            r"[a-z][a-z0-9-]{0,62}",
            name,
        )
    ):
        raise InfraError(
            "Invalid artifacts.repository_name."
        )


def validate_storage_config(
    storage: dict[str, Any],
) -> None:
    name = storage.get(
        "bucket_name"
    )

    if name is None:
        return

    if (
        not isinstance(name, str)
        or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]",
            name,
        )
    ):
        raise InfraError(
            "Invalid storage.bucket_name."
        )


def validate_cloud_run_config(
    cloud_run: dict[str, Any],
) -> None:
    service_name = cloud_run.get(
        "service_name"
    )

    if (
        not isinstance(service_name, str)
        or not re.fullmatch(
            r"[a-z](?:[a-z0-9-]{0,47}[a-z0-9])?",
            service_name,
        )
    ):
        raise InfraError(
            "Invalid cloud_run.service_name."
        )

    if cloud_run.get("cpu") != "1":
        raise InfraError(
            "cloud_run.cpu must be '1'."
        )

    if cloud_run.get("memory") not in {
        "512Mi",
        "1Gi",
    }:
        raise InfraError(
            "cloud_run.memory must be 512Mi or 1Gi."
        )

    min_instances = cloud_run.get(
        "min_instances"
    )

    max_instances = cloud_run.get(
        "max_instances"
    )

    concurrency = cloud_run.get(
        "concurrency"
    )

    timeout = cloud_run.get(
        "timeout_seconds"
    )

    if (
        type(min_instances) is not int
        or min_instances != 0
    ):
        raise InfraError(
            "cloud_run.min_instances must be 0."
        )

    if (
        type(max_instances) is not int
        or not 1 <= max_instances <= 2
    ):
        raise InfraError(
            "cloud_run.max_instances must be 1 or 2."
        )

    if (
        type(concurrency) is not int
        or not 1 <= concurrency <= 10
    ):
        raise InfraError(
            "cloud_run.concurrency must be between 1 and 10."
        )

    if (
        type(timeout) is not int
        or not 1 <= timeout <= 300
    ):
        raise InfraError(
            "cloud_run.timeout_seconds must be between "
            "1 and 300."
        )

    if cloud_run.get("billing") != "request-based":
        raise InfraError(
            "cloud_run.billing must be request-based."
        )


def validate_inference_config(
    inference: dict[str, Any],
) -> None:
    mode = inference.get(
        "mode"
    )

    if not mode:
        raise InfraError(
            "Set inference.mode explicitly to 'developer' "
            "or 'vertex' after checking model availability, "
            "cost and data privacy."
        )

    if mode not in {
        "developer",
        "vertex",
    }:
        raise InfraError(
            "inference.mode must be 'developer' or 'vertex'."
        )

    model = inference.get(
        "model"
    )

    if (
        not isinstance(model, str)
        or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}",
            model,
        )
    ):
        raise InfraError(
            "inference.model must be a valid model identifier."
        )

    location = inference.get(
        "location"
    )

    if location not in {
        None,
        "global",
    }:
        raise InfraError(
            "inference.location must be global or null."
        )


def validate_budget_config(
    budget: dict[str, Any],
) -> None:
    thresholds = budget.get(
        "alert_thresholds"
    )

    if thresholds != [
        0.5,
        0.8,
        1.0,
    ]:
        raise InfraError(
            "budget.alert_thresholds must be "
            "[0.5, 0.8, 1.0]."
        )

    currency = budget.get(
        "currency",
        "USD",
    )

    if (
        not isinstance(currency, str)
        or not re.fullmatch(
            r"[A-Z]{3}",
            currency,
        )
    ):
        raise InfraError(
            "budget.currency must be a valid "
            "three-letter currency code."
        )

    if "amount" in budget:
        if "amount_usd" in budget:
            raise InfraError(
                "Use budget.amount or budget.amount_usd, "
                "not both."
            )

        field = "amount"
        amount = budget["amount"]

    else:
        field = "amount_usd"
        amount = budget.get(field)

        if currency != "USD":
            raise InfraError(
                "budget.amount_usd requires USD currency."
            )

    if (
        type(amount) not in {int, float}
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise InfraError(
            f"budget.{field} must be greater than zero."
        )

    if abs(
        amount - round(amount, 2)
    ) > 1e-9:
        raise InfraError(
            f"budget.{field} must have at most "
            "two decimal places."
        )


def register_secret(
    value: str | None,
) -> None:
    if value and len(value) >= 4:
        _REGISTERED_SECRETS.add(
            value
        )


def clear_registered_secrets() -> None:
    _REGISTERED_SECRETS.clear()


def redact_text(value: str) -> str:
    if not value:
        return value

    redacted = value

    for secret in sorted(
        _REGISTERED_SECRETS,
        key=len,
        reverse=True,
    ):
        redacted = redacted.replace(
            secret,
            "[REDACTED]",
        )

    redacted = _DATABASE_URL_CREDENTIALS.sub(
        r"\g<prefix>[REDACTED]\g<suffix>",
        redacted,
    )

    return _SENSITIVE_ASSIGNMENT.sub(
        r"\1\2[REDACTED]",
        redacted,
    )


def _is_sensitive_flag(
    value: str,
) -> bool:
    name = (
        value.lstrip("-")
        .split("=", 1)[0]
        .lower()
    )

    if name in _SAFE_SECRET_FLAGS:
        return False

    return any(
        part in name
        for part in _SENSITIVE_FLAG_PARTS
    )


def format_command(
    command: Sequence[str],
) -> str:
    parts: list[str] = []
    redact_next = False

    for raw_part in command:
        part = str(raw_part)

        if redact_next:
            parts.append(
                "[REDACTED]"
            )

            redact_next = False

            continue

        if (
            part.startswith("-")
            and "=" in part
        ):
            flag, _ = part.split(
                "=",
                1,
            )

            if _is_sensitive_flag(flag):
                parts.append(
                    f"{flag}=[REDACTED]"
                )

                continue

        if (
            part.startswith("-")
            and _is_sensitive_flag(part)
        ):
            parts.append(part)
            redact_next = True

            continue

        if (
            not part.startswith("-")
            and _is_sensitive_flag(part)
        ):
            parts.append(
                "[REDACTED]"
            )

            continue

        parts.append(
            redact_text(part)
        )

    return " ".join(parts)


def _failure_detail(
    result: subprocess.CompletedProcess[str],
) -> str:
    stderr = redact_text(
        (result.stderr or "").strip()
    )

    if len(stderr) > 4000:
        stderr = stderr[:4000] + "..."

    return stderr


def command_failure(
    result: subprocess.CompletedProcess[str],
    action: str,
) -> InfraError:
    detail = _failure_detail(
        result
    )

    message = (
        f"{action} failed with exit code "
        f"{result.returncode}."
    )

    if detail:
        message = (
            f"{message}\n{detail}"
        )

    return InfraError(
        message
    )


def ensure_command_succeeded(
    result: subprocess.CompletedProcess[str],
    action: str,
) -> None:
    if result.returncode != 0:
        raise command_failure(
            result,
            action,
        )


def is_missing_resource(
    result: subprocess.CompletedProcess[str],
    action: str,
) -> bool:
    if result.returncode == 0:
        return False

    output = (
        f"{result.stderr or ''}\n"
        f"{result.stdout or ''}"
    ).lower()

    if any(
        re.search(pattern, output)
        for pattern in _PERMISSION_PATTERNS
    ):
        raise command_failure(
            result,
            action,
        )

    if any(
        re.search(pattern, output)
        for pattern in _NOT_FOUND_PATTERNS
    ):
        return True

    raise command_failure(
        result,
        f"{action}: the CLI did not identify "
        "a missing resource",
    )


def resolve_command(
    command: Sequence[str],
) -> list[str] | str:
    if not command:
        raise InfraError(
            "Cannot execute an empty command."
        )

    arguments = [
        str(argument)
        for argument in command
    ]

    executable = shutil.which(
        arguments[0]
    )

    if executable is None:
        raise InfraError(
            f"Required executable not found: {arguments[0]}"
        )

    arguments[0] = executable

    # Native executables are launched directly.
    if os.name != "nt":
        return arguments

    suffix = Path(
        executable
    ).suffix.lower()

    if suffix not in {
        ".cmd",
        ".bat",
    }:
        return arguments

    # Windows CLI wrappers require cmd.exe parsing.
    # Reject characters that can trigger additional
    # shell expansion instead of accepting arbitrary syntax.
    unsafe_characters = (
        '"',
        "%",
        "!",
        "\r",
        "\n",
        "\x00",
    )

    for argument in arguments:
        if any(
            character in argument
            for character in unsafe_characters
        ):
            raise InfraError(
                "Unsupported character in a Windows "
                "batch command argument."
            )

        if argument.endswith("\\"):
            raise InfraError(
                "Windows batch arguments must not end "
                "with a backslash."
            )

    cmd_executable = os.environ.get(
        "COMSPEC"
    )

    if not cmd_executable:
        system_root = os.environ.get(
            "SystemRoot",
            r"C:\Windows",
        )

        cmd_executable = str(
            Path(system_root)
            / "System32"
            / "cmd.exe"
        )

    quoted_arguments = " ".join(
        f'"{argument}"'
        for argument in arguments
    )

    return (
        f'"{cmd_executable}" '
        f'/d /v:off /s /c "{quoted_arguments}"'
    )


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
    input_text: str | None = None,
    secrets: Iterable[str] = (),
) -> subprocess.CompletedProcess[str]:
    for secret in secrets:
        register_secret(secret)

    printable_command = format_command(
        command
    )

    print(
        f"$ {printable_command}",
        flush=True,
    )

    resolved_env = os.environ.copy()

    resolved_env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "CLOUDSDK_CORE_DISABLE_PROMPTS": "1",
        }
    )

    if env:
        resolved_env.update(env)

    resolved = resolve_command(
        command
    )

    try:
        result = subprocess.run(
            resolved,
            cwd=cwd or REPOSITORY_ROOT,
            env=resolved_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            capture_output=True,
            input=input_text,
            shell=False,
        )

    except FileNotFoundError:
        raise InfraError(
            f"Required executable not found: {command[0]}"
        ) from None

    except OSError as error:
        raise InfraError(
            f"Could not execute {printable_command}: "
            f"{redact_text(str(error))}"
        ) from None

    if check:
        ensure_command_succeeded(
            result,
            printable_command,
        )

    if not capture_output:
        if result.stdout:
            print(
                redact_text(result.stdout),
                end="",
                flush=True,
            )

        if result.stderr:
            print(
                redact_text(result.stderr),
                end="",
                file=sys.stderr,
                flush=True,
            )

    return result


def require_commands(
    names: Iterable[str],
) -> None:
    missing = [
        name
        for name in names
        if shutil.which(name) is None
    ]

    if missing:
        raise InfraError(
            "Missing required executables: "
            + ", ".join(missing)
        )


def require_git_clean() -> None:
    result = run_command(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )

    if result.stdout.strip():
        raise InfraError(
            "Git working tree is not clean."
        )


def base_parser(
    description: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=description
    )

    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "Local configuration JSON "
            "(default: infra/config.local.json)"
        ),
    )

    return parser


def main_entry(
    parser: argparse.ArgumentParser,
    operation: Any,
) -> None:
    args = parser.parse_args()

    try:
        config = load_config(
            args.config
        )

        operation(config)

    except InfraError as error:
        print(
            f"Error: {redact_text(str(error))}",
            file=sys.stderr,
        )

        raise SystemExit(1) from None

    except (KeyboardInterrupt, EOFError):
        print(
            "\nOperation cancelled.",
            file=sys.stderr,
        )

        raise SystemExit(130) from None

    finally:
        clear_registered_secrets()