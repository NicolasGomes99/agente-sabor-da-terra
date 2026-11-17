from pathlib import Path
from shutil import copyfileobj
from typing import BinaryIO

from .base import validate_storage_key


class LocalDocumentStorage:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def save(self, key: str, source: BinaryIO) -> None:
        path = self._path_for(key)
        self.directory.mkdir(parents=True, exist_ok=True)

        destination = path.open("xb")
        try:
            with destination:
                copyfileobj(source, destination)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def open(self, key: str) -> BinaryIO:
        return self._path_for(key).open("rb")

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        validate_storage_key(key)
        path = self.directory / key
        if path.resolve().parent != self.directory:
            raise ValueError("Storage key resolves outside the storage directory.")
        return path
