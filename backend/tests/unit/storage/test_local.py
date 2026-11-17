from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from api.storage.local import LocalDocumentStorage


class FailingSource(BytesIO):
    def read(self, size: int = -1, /) -> bytes:
        if self.tell() > 0:
            raise OSError("read failed")
        return super().read(3)


def test_save_copies_from_current_position(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path / "documents")
    with BytesIO(b"prefix-content") as source:
        source.seek(len(b"prefix-"))
        storage.save("key", source)
        assert not source.closed

    with storage.open("key") as saved:
        assert saved.read() == b"content"


def test_save_preserves_existing_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    with BytesIO(b"original") as original, BytesIO(b"replacement") as replacement:
        storage.save("key", original)
        with pytest.raises(FileExistsError):
            storage.save("key", replacement)

    with storage.open("key") as saved:
        assert saved.read() == b"original"


def test_save_removes_partial_file_on_read_failure(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    with FailingSource(b"content") as source, pytest.raises(OSError, match="read failed"):
        storage.save("key", source)

    assert not (tmp_path / "key").exists()


def test_open_raises_for_missing_file(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(FileNotFoundError):
        storage.open("missing")


def test_delete_removes_file_and_can_be_repeated(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    with BytesIO(b"content") as source:
        storage.save("key", source)

    storage.delete("key")
    assert not (tmp_path / "key").exists()
    storage.delete("key")


@pytest.mark.parametrize(
    "key", ["../arquivo", "pasta/arquivo", r"C:\arquivo", "NUL.pdf", "COM1", "LPT¹.txt"]
)
def test_operations_reject_invalid_keys(tmp_path: Path, key: str) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with BytesIO(b"content") as source, pytest.raises(ValueError):
        storage.save(key, source)
    with pytest.raises(ValueError):
        storage.open(key)
    with pytest.raises(ValueError):
        storage.delete(key)


def test_operations_accept_uuid_hex_key(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    key = uuid4().hex

    with BytesIO(b"content") as source:
        storage.save(key, source)
    with storage.open(key) as saved:
        assert saved.read() == b"content"
    storage.delete(key)

    assert not (tmp_path / key).exists()
