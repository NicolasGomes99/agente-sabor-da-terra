from os import SEEK_END
from shutil import copyfileobj
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud.storage import Bucket
from google.cloud.storage.fileio import BlobReader

from .base import validate_storage_key

TRANSFER_CHUNK_SIZE = 4 * 1024**2
UPLOAD_SPOOL_SIZE = 1024**2


class GCSDocumentStorage:
    def __init__(self, bucket: Bucket) -> None:
        self.bucket = bucket

    def save(self, key: str, source: BinaryIO) -> None:
        validate_storage_key(key)
        try:
            blob = self.bucket.blob(key, chunk_size=TRANSFER_CHUNK_SIZE)
            if source.seekable() and source.tell() == 0:
                size = source.seek(0, SEEK_END)
                source.seek(0)
                blob.upload_from_file(source, size=size, if_generation_match=0)
            else:
                with SpooledTemporaryFile(max_size=UPLOAD_SPOOL_SIZE, mode="w+b") as upload:
                    copyfileobj(source, upload)
                    size = upload.tell()
                    upload.seek(0)
                    blob.upload_from_file(upload, size=size, if_generation_match=0)
        except PreconditionFailed as error:
            raise FileExistsError(key) from error

    def open(self, key: str) -> BlobReader:
        validate_storage_key(key)
        blob = self.bucket.get_blob(key)
        if blob is None:
            raise FileNotFoundError(key)
        return BlobReader(blob, chunk_size=TRANSFER_CHUNK_SIZE, raw_download=True)

    def delete(self, key: str) -> None:
        validate_storage_key(key)
        try:
            self.bucket.blob(key).delete()
        except NotFound:
            pass
