from pathlib import Path

import pytest

from api.config import (
    get_document_storage_backend,
    get_document_storage_bucket,
    get_document_storage_dir,
    get_document_upload_max_bytes,
)


def test_upload_limit_defaults_to_ten_mib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_UPLOAD_MAX_BYTES", raising=False)

    assert get_document_upload_max_bytes() == 10 * 1024**2


@pytest.mark.parametrize("limit", [1, 30 * 1024**2])
def test_upload_limit_accepts_bounds(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_MAX_BYTES", str(limit))
    assert get_document_upload_max_bytes() == limit


@pytest.mark.parametrize("value", ["", "invalid", "0", "-1", str(30 * 1024**2 + 1)])
def test_upload_limit_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_MAX_BYTES", value)

    with pytest.raises(RuntimeError, match="DOCUMENT_UPLOAD_MAX_BYTES"):
        get_document_upload_max_bytes()


def test_storage_backend_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_STORAGE_BACKEND", raising=False)

    assert get_document_storage_backend() == "local"


@pytest.mark.parametrize("backend", ["local", "gcs"])
def test_storage_backend_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", f"  {backend}  ")

    assert get_document_storage_backend() == backend


@pytest.mark.parametrize("value", ["", "  ", "s3"])
def test_storage_backend_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", value)

    with pytest.raises(RuntimeError, match="DOCUMENT_STORAGE_BACKEND"):
        get_document_storage_backend()


def test_storage_dir_returns_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", "  data/documents  ")

    assert get_document_storage_dir() == Path("data/documents")


@pytest.mark.parametrize("value", [None, "  "])
def test_storage_dir_requires_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("DOCUMENT_STORAGE_DIR", raising=False)
    else:
        monkeypatch.setenv("DOCUMENT_STORAGE_DIR", value)

    with pytest.raises(RuntimeError, match="DOCUMENT_STORAGE_DIR"):
        get_document_storage_dir()


def test_storage_bucket_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BUCKET", "  documents-bucket  ")

    assert get_document_storage_bucket() == "documents-bucket"


@pytest.mark.parametrize("value", [None, "  "])
def test_storage_bucket_requires_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("DOCUMENT_STORAGE_BUCKET", raising=False)
    else:
        monkeypatch.setenv("DOCUMENT_STORAGE_BUCKET", value)

    with pytest.raises(RuntimeError, match="DOCUMENT_STORAGE_BUCKET"):
        get_document_storage_bucket()
