import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILENAME = "config.local.json"
DEFAULT_CONFIG = REPOSITORY_ROOT / "infra" / "config.example.json"
SENSITIVE_KEY_PARTS = ("password", "secret", "key", "token", "credential")


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
    if len(project_id) > 30 or not all(char.isalnum() or char == "-" for char in project_id):
        raise InfraError("project_id is not a valid Google Cloud Project ID.")
    if config["region"].strip() != "us-central1":
        raise InfraError("Only the planned region us-central1 is supported.")

    inference = config["inference"]
    mode = inference.get("mode")
    if mode not in {"developer", "vertex"}:
        raise InfraError("inference.mode must be 'developer' or 'vertex'.")
    model = inference.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InfraError("inference.model must be a non-empty string.")

    thresholds = config["budget"].get("alert_thresholds")
    if not isinstance(thresholds, list) or thresholds != [0.5, 0.8, 1.0]:
        raise InfraError("budget.alert_thresholds must be [0.5, 0.8, 1.0].")


def redact_sensitive(value: str) -> str:
    for key_part in SENSITIVE_KEY_PARTS:
        if key_part in value.lower():
            return "[REDACTED]"
    return value


def format_command(command: Sequence[str]) -> str:
    return " ".join(redact_sensitive(str(part)) for part in command)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
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
        )
    except FileNotFoundError as error:
        executable = str(command[0])
        raise InfraError(f"Required executable not found: {executable}") from error
    except subprocess.CalledProcessError as error:
        raise InfraError(
            f"Command failed with exit code {error.returncode}: {format_command(command)}"
        ) from error


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
