from io import BytesIO
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from google.api_core.exceptions import Forbidden, NotFound, PreconditionFailed
from google.cloud.storage import Blob, Bucket, Client
from google.cloud.storage.fileio import BlobReader
from requests import Response, Session

from api.storage.gcs import GCSDocumentStorage


class NonSeekableStream(BytesIO):
    def seekable(self) -> bool:
        return False

    def seek(self, *args, **kwargs) -> int:
        raise AssertionError("The source must be read sequentially.")


@pytest.mark.parametrize("source_type", ["at_start", "advanced", "non_seekable"])
def test_save_uploads_remaining_bytes_with_create_only_precondition(source_type: str) -> None:
    bucket = Mock(spec=Bucket)
    blob = bucket.blob.return_value
    storage = GCSDocumentStorage(bucket)

    def upload(stream, *, size, if_generation_match):
        assert stream.tell() == 0
        assert stream.read() == b"content"
        assert size == len(b"content")
        assert if_generation_match == 0

    blob.upload_from_file.side_effect = upload
    source_class = NonSeekableStream if source_type == "non_seekable" else BytesIO
    initial_bytes = b"prefix-content" if source_type == "advanced" else b"content"
    with source_class(initial_bytes) as source:
        if source_type == "advanced":
            source.seek(len(b"prefix-"))
        storage.save("key", source)
        assert not source.closed

    blob.upload_from_file.assert_called_once()
    bucket.blob.assert_called_once_with("key", chunk_size=4 * 1024**2)


def test_save_from_advanced_stream_through_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client.create_anonymous_client()
    storage = GCSDocumentStorage(client.bucket("documents"))
    response = Response()
    response.status_code = 200
    response._content = b'{"name": "key"}'
    request = Mock(return_value=response)
    monkeypatch.setattr(Session, "request", request)

    with BytesIO(b"skip-this-prefix|payload") as source:
        source.seek(len(b"skip-this-prefix|"))
        storage.save("key", source)
        assert not source.closed

    uploads = [entry for entry in request.call_args_list if entry.args[0] == "POST"]
    assert len(uploads) == 1
    arguments = uploads[0].kwargs
    query = parse_qs(urlsplit(uploads[0].args[1]).query)
    assert query["ifGenerationMatch"] == ["0"]
    assert query["uploadType"] == ["multipart"]
    assert b"payload" in arguments["data"]
    assert b"skip-this-prefix" not in arguments["data"]


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
        assert reader._chunk_size == 4 * 1024**2

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
