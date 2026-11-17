from io import BytesIO
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Forbidden, NotFound, PreconditionFailed
from google.cloud.storage import Blob, Bucket
from google.cloud.storage.fileio import BlobReader

from api.storage.gcs import GCSDocumentStorage


def test_save_uploads_with_create_only_precondition() -> None:
    bucket = Mock(spec=Bucket)
    blob = bucket.blob.return_value
    storage = GCSDocumentStorage(bucket)

    with BytesIO(b"content") as source:
        storage.save("key", source)
        blob.upload_from_file.assert_called_once_with(source, if_generation_match=0)

    bucket.blob.assert_called_once_with("key")


def test_save_raises_when_key_already_exists() -> None:
    bucket = Mock(spec=Bucket)
    bucket.blob.return_value.upload_from_file.side_effect = PreconditionFailed("exists")
    storage = GCSDocumentStorage(bucket)

    with BytesIO(b"content") as source, pytest.raises(FileExistsError):
        storage.save("key", source)


def test_open_returns_blob_reader() -> None:
    bucket = Mock(spec=Bucket)
    bucket.get_blob.return_value = Blob("key", bucket)
    storage = GCSDocumentStorage(bucket)

    with storage.open("key") as reader:
        assert isinstance(reader, BlobReader)

    bucket.get_blob.assert_called_once_with("key")


def test_open_raises_when_key_is_missing() -> None:
    bucket = Mock(spec=Bucket)
    bucket.get_blob.return_value = None
    storage = GCSDocumentStorage(bucket)

    with pytest.raises(FileNotFoundError):
        storage.open("missing")


def test_delete_removes_blob_by_key() -> None:
    bucket = Mock(spec=Bucket)
    storage = GCSDocumentStorage(bucket)

    storage.delete("key")

    bucket.blob.assert_called_once_with("key")
    bucket.blob.return_value.delete.assert_called_once_with()


def test_delete_accepts_missing_blob() -> None:
    bucket = Mock(spec=Bucket)
    bucket.blob.return_value.delete.side_effect = NotFound("missing")
    storage = GCSDocumentStorage(bucket)

    storage.delete("missing")

    bucket.blob.return_value.delete.assert_called_once_with()


def test_delete_propagates_permission_error() -> None:
    bucket = Mock(spec=Bucket)
    bucket.blob.return_value.delete.side_effect = Forbidden("permission denied")
    storage = GCSDocumentStorage(bucket)

    with pytest.raises(Forbidden, match="permission denied"):
        storage.delete("key")


def test_operations_reject_invalid_key_before_calling_bucket() -> None:
    bucket = Mock(spec=Bucket)
    storage = GCSDocumentStorage(bucket)
    key = "../arquivo"

    with BytesIO(b"content") as source, pytest.raises(ValueError):
        storage.save(key, source)
    with pytest.raises(ValueError):
        storage.open(key)
    with pytest.raises(ValueError):
        storage.delete(key)

    assert bucket.mock_calls == []
