import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_AGENT_MODEL = "gemini-3.8-flash"
PERNAMBUCO_TIMEZONE = timezone(timedelta(hours=-3), name="America/Recife")


def get_agent_model() -> str:
    configured = os.getenv("GEMINI_AGENT_MODEL")
    if configured is None:
        return DEFAULT_AGENT_MODEL

    model = configured.strip()
    if not model:
        raise RuntimeError("GEMINI_AGENT_MODEL must not be blank.")
    return model


def is_enterprise_enabled() -> bool:
    for env_name in ("GOOGLE_GENAI_USE_ENTERPRISE", "GOOGLE_GENAI_USE_VERTEXAI"):
        raw = os.getenv(env_name)
        if raw is not None and raw.strip().lower() in {"1", "true", "yes"}:
            return True
    return False


def to_pernambuco_date(value: datetime | date | str) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(PERNAMBUCO_TIMEZONE).date()
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Date reference must not be blank.")
        if "T" in cleaned or " " in cleaned:
            normalized = cleaned.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(normalized)
            return to_pernambuco_date(parsed_dt)
        return date.fromisoformat(cleaned)

    raise TypeError(f"Unsupported date value: {type(value)!r}")
