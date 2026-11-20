
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_DOCUMENT_UPLOAD_MAX_BYTES = 10 * 1024**2
MAX_DOCUMENT_UPLOAD_BYTES = 30 * 1024**2


def get_document_upload_max_bytes() -> int:
    max_bytes = globals()["MAX_DOCUMENT_UPLOAD_BYTES"]

    configured = os.getenv("DOCUMENT_UPLOAD_MAX_BYTES")
    if configured is None:
        return DEFAULT_DOCUMENT_UPLOAD_MAX_BYTES

    error_message = (
        f"DOCUMENT_UPLOAD_MAX_BYTES must be between 1 and {max_bytes}."
    )
    try:
        limit = int(configured)
    except ValueError as error:
        raise RuntimeError(error_message) from error

    if not 1 <= limit <= max_bytes:
        raise RuntimeError(error_message)

    return limit


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


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 768
MAX_EMBEDDING_DIMENSIONS = 3072
DEFAULT_RAG_SEMANTIC_TOP_K = 8


def get_embedding_model() -> str:
    configured = os.getenv("GEMINI_EMBEDDING_MODEL")
    if configured is None:
        return DEFAULT_EMBEDDING_MODEL
    model = configured.strip()
    if not model:
        raise RuntimeError("GEMINI_EMBEDDING_MODEL must not be blank.")
    return model


def get_embedding_dimensions() -> int:
    configured = os.getenv("GEMINI_EMBEDDING_DIMENSIONS")
    if configured is None:
        return DEFAULT_EMBEDDING_DIMENSIONS
    error_message = (
        f"GEMINI_EMBEDDING_DIMENSIONS must be between 1 and {MAX_EMBEDDING_DIMENSIONS}."
    )
    try:
        dimensions = int(configured)
    except ValueError as error:
        raise RuntimeError(error_message) from error
    if not 1 <= dimensions <= MAX_EMBEDDING_DIMENSIONS:
        raise RuntimeError(error_message)
    return dimensions


def get_rag_semantic_top_k() -> int:
    configured = os.getenv("RAG_SEMANTIC_TOP_K")
    if configured is None:
        return DEFAULT_RAG_SEMANTIC_TOP_K
    error_message = "RAG_SEMANTIC_TOP_K must be an integer greater than or equal to 1."
    try:
        top_k = int(configured)
    except ValueError as error:
        raise RuntimeError(error_message) from error
    if top_k < 1:
        raise RuntimeError(error_message)
    return top_k
