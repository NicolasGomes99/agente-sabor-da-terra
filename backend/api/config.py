import os
from pathlib import Path
from typing import Literal


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


def get_document_storage_backend() -> Literal["local", "gcs"]:
    backend = os.getenv("DOCUMENT_STORAGE_BACKEND", "local").strip()
    if backend == "local" or backend == "gcs":
        return backend
    raise RuntimeError("DOCUMENT_STORAGE_BACKEND must be 'local' or 'gcs'.")


def get_document_storage_dir() -> Path:
    directory = os.getenv("DOCUMENT_STORAGE_DIR", "").strip()
    if not directory:
        raise RuntimeError("DOCUMENT_STORAGE_DIR must be set.")
    return Path(directory)


def get_document_storage_bucket() -> str:
    bucket = os.getenv("DOCUMENT_STORAGE_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("DOCUMENT_STORAGE_BUCKET must be set.")
    return bucket
