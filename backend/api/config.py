
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        raise RuntimeError("DATABASE_URL must be set.")
    return url.strip()


def get_cors_allowed_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    ]
