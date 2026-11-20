import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILENAME = "config.local.json"
DEFAULT_CONFIG = REPOSITORY_ROOT / "infra" / "config.example.json"

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
_SAFE_SECRET_FLAGS = {"secret", "secret-name", "secret-id", "secrets"}
_REGISTERED_SECRETS: set[str] = set()

_DATABASE_URL_CREDENTIALS = re.compile(
    r"(?P<prefix>[A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]+:)(?P<secret>[^@\s]+)(?P<suffix>@)"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|credential)\b"
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
    r"could not fetch resource",
    r"\b404\b",
    r"unknown service account",
    r"unknown project",
    r"unknown instance",
)


class InfraError(RuntimeError):
    pass


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or REPOSITORY_ROOT / "infra" / CONFIG_FILENAME
    if not config_path.exists():
        raise InfraError(
            f"Configuration file not found: {config_path}. "
            f"Copy {DEFAULT_CONFIG} to {config_path} and fill project_id."
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InfraError(f"Invalid JSON in {config_path}: {error}") from error

    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required_sections = {
        "project_id": str,
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
            raise InfraError(f"Configuration '{name}' must be {expected_type.__name__}.")

    project_id = config["project_id"].strip()
    if not project_id or project_id == "sabor-da-terra":
        raise InfraError("Set a unique project_id in the local configuration.")
    if (
        len(project_id) < 6
        or len(project_id) > 30
        or not project_id[0].isalpha()
        or not project_id.isascii()
        or not all(char.islower() or char.isdigit() or char == "-" for char in project_id)
        or project_id.startswith("-")
        or project_id.endswith("-")
        or "--" in project_id
    ):
        raise InfraError("project_id is not a valid Google Cloud Project ID.")
    if config["region"].strip() != "us-central1":
        raise InfraError("Only the planned region us-central1 is supported.")

    billing_account_id = str(config.get("billing_account_id", "")).strip()
    if not billing_account_id or "X" in billing_account_id.upper():
        raise InfraError("Set billing_account_id in the local configuration.")

    validate_database_config(config["database"])

    inference = config["inference"]
    mode = str(inference.get("mode", "")).strip()
    if not mode:
        raise InfraError(
            "Set inference.mode explicitly to 'developer' or 'vertex' after checking "
            "model availability, cost and data privacy. There is no implicit default."
        )
    if mode not in {"developer", "vertex"}:
        raise InfraError("inference.mode must be 'developer' or 'vertex'.")
    model = inference.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InfraError("inference.model must be a non-empty string.")
    location = inference.get("location")
    if location is not None and (not isinstance(location, str) or not location.strip()):
        raise InfraError("inference.location must be a non-empty string when set.")

    thresholds = config["budget"].get("alert_thresholds")
    if not isinstance(thresholds, list) or thresholds != [0.5, 0.8, 1.0]:
        raise InfraError("budget.alert_thresholds must be [0.5, 0.8, 1.0].")
    amount = config["budget"].get("amount_usd")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise InfraError("budget.amount_usd must be greater than zero.")


def validate_database_config(database: dict[str, Any]) -> None:
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
        if not isinstance(value, expected_type) or (
            isinstance(value, str) and not value.strip()
        ):
            raise InfraError(
                f"Configuration 'database.{name}' must be a non-empty "
                f"{expected_type.__name__}."
            )

    for name in ("instance_name", "database_name", "migrator_user", "application_user"):
        value = database[name]
        if len(value) > 63 or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
            raise InfraError(
                f"database.{name} must be a valid PostgreSQL identifier "
                "with at most 63 characters."
            )
    if database["admin_user"] != "postgres":
        raise InfraError("database.admin_user must be 'postgres'.")
    if len({database["migrator_user"], database["application_user"]}) != 2:
        raise InfraError("The migrator and application users must be different.")
    if database["storage_size_gb"] < 10:
        raise InfraError("database.storage_size_gb must be at least 10.")
    if database["backup_enabled"]:
        raise InfraError(
            "database.backup_enabled must be false for the planned environment."
        )
    if not database["deletion_protection"]:
        raise InfraError(
            "database.deletion_protection must be true for the planned environment."
        )
    if database["tier"] != "db-f1-micro":
        raise InfraError("database.tier must be db-f1-micro for the planned environment.")


def register_secret(value: str | None) -> None:
    if value and len(value) >= 4:
        _REGISTERED_SECRETS.add(value)


def clear_registered_secrets() -> None:
    _REGISTERED_SECRETS.clear()


def redact_text(value: str) -> str:
    if not value:
        return value

    redacted = value
    for secret in sorted(_REGISTERED_SECRETS, key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _DATABASE_URL_CREDENTIALS.sub(
        r"\g<prefix>[REDACTED]\g<suffix>",
        redacted,
    )
    return _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)


def _is_sensitive_flag(value: str) -> bool:
    name = value.lstrip("-").split("=", 1)[0].lower()
    if name in _SAFE_SECRET_FLAGS:
        return False
    return any(part in name for part in _SENSITIVE_FLAG_PARTS)


def format_command(command: Sequence[str]) -> str:
    parts: list[str] = []
    redact_next = False
    for raw_part in command:
        part = str(raw_part)
        if redact_next:
            parts.append("[REDACTED]")
            redact_next = False
            continue
        if part.startswith("-") and "=" in part:
            flag, _ = part.split("=", 1)
            if _is_sensitive_flag(flag):
                parts.append(f"{flag}=[REDACTED]")
                continue
        if part.startswith("-") and _is_sensitive_flag(part):
            parts.append(part)
            redact_next = True
            continue
        if not part.startswith("-") and _is_sensitive_flag(part):
            parts.append("[REDACTED]")
            continue
        parts.append(redact_text(part))
    return " ".join(parts)


def _failure_detail(result: subprocess.CompletedProcess[str]) -> str:
    stderr = redact_text((result.stderr or "").strip())
    if len(stderr) > 2000:
        stderr = stderr[:2000] + "..."
    return stderr


def command_failure(result: subprocess.CompletedProcess[str], action: str) -> InfraError:
    detail = _failure_detail(result)
    message = f"{action} failed with exit code {result.returncode}."
    if detail:
        message = f"{message}\n{detail}"
    return InfraError(message)


def ensure_command_succeeded(
    result: subprocess.CompletedProcess[str],
    action: str,
) -> None:
    if result.returncode != 0:
        raise command_failure(result, action)


def is_missing_resource(
    result: subprocess.CompletedProcess[str],
    action: str,
) -> bool:
    """Return True only when the CLI clearly reports a missing resource.

    Permission, authentication and connectivity failures are raised instead of
    being confused with an absent resource.
    """
    if result.returncode == 0:
        return False

    output = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    if any(re.search(pattern, output) for pattern in _PERMISSION_PATTERNS):
        raise command_failure(result, action)
    if any(re.search(pattern, output) for pattern in _NOT_FOUND_PATTERNS):
        return True
    raise command_failure(
        result,
        f"{action} (the CLI output did not identify a missing resource)",
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

    print(f"$ {format_command(command)}", flush=True)
    resolved_env = os.environ.copy()
    if env:
        resolved_env.update(env)
    try:
        return subprocess.run(
            list(command),
            cwd=cwd or REPOSITORY_ROOT,
            env=resolved_env,
            text=True,
            check=check,
            capture_output=capture_output,
            input=input_text,
        )
    except FileNotFoundError as error:
        executable = str(command[0])
        raise InfraError(f"Required executable not found: {executable}") from None
    except subprocess.CalledProcessError as error:
        detail = ""
        if error.stderr:
            detail = redact_text(str(error.stderr).strip())
            if len(detail) > 2000:
                detail = detail[:2000] + "..."
        message = (
            f"Command failed with exit code {error.returncode}: "
            f"{format_command(command)}"
        )
        if detail:
            message = f"{message}\n{detail}"
        raise InfraError(message) from None


def require_commands(names: Iterable[str]) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise InfraError("Missing required executables: " + ", ".join(missing))


def require_git_clean() -> None:
    result = run_command(
        ["git", "status", "--porcelain"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    if result.stdout.strip():
        raise InfraError("Git working tree is not clean.")


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=Path,
        help="Local configuration JSON (default: infra/config.local.json)",
    )
    return parser


def main_entry(parser: argparse.ArgumentParser, operation: Any) -> None:
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        operation(config)
    except InfraError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
