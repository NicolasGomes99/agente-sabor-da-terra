from pathlib import Path

import pytest

from api.config import (
    get_document_storage_backend,
    get_document_storage_bucket,
    get_document_storage_dir,
)


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
