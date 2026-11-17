from typing import BinaryIO

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud.storage import Bucket
from google.cloud.storage.fileio import BlobReader

from .base import validate_storage_key


class GCSDocumentStorage:
    def __init__(self, bucket: Bucket) -> None:
        self.bucket = bucket

    def save(self, key: str, source: BinaryIO) -> None:
        validate_storage_key(key)
        try:
            self.bucket.blob(key).upload_from_file(source, if_generation_match=0)
        except PreconditionFailed as error:
            raise FileExistsError(key) from error

    def open(self, key: str) -> BlobReader:
        validate_storage_key(key)
        blob = self.bucket.get_blob(key)
        if blob is None:
            raise FileNotFoundError(key)
        return BlobReader(blob, raw_download=True)

    def delete(self, key: str) -> None:
        validate_storage_key(key)
        try:
            self.bucket.blob(key).delete()
        except NotFound:
            pass
