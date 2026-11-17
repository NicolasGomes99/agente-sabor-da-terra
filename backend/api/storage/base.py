from pathlib import PureWindowsPath
from typing import BinaryIO, Protocol


class DocumentReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def close(self) -> None: ...


class DocumentStorage(Protocol):
    def save(self, key: str, source: BinaryIO) -> None:
        """Copy from the current position without taking ownership of source."""
        ...

    def open(self, key: str) -> DocumentReader:
        """Return a binary stream that the caller must close."""
        ...

    def delete(self, key: str) -> None:
        """Remove the file if present."""
        ...


def validate_storage_key(key: str) -> None:
    path = PureWindowsPath(key)
    if (
        not key
        or key in {".", ".."}
        or any(character in key for character in '/\\:<>"|?*')
        or any(ord(character) < 32 for character in key)
        or key.endswith((".", " "))
        or path.is_reserved()
    ):
        raise ValueError("Storage key must be a single portable filename.")
