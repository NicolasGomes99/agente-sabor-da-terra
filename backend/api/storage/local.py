import os
from pathlib import Path
from shutil import copyfileobj
from typing import BinaryIO

from .base import validate_storage_key


def _open_windows_reader_fd(path: str, flags: int) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    generic_read = 0x80000000
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    file_share_delete = 0x00000004
    open_existing = 3
    file_attribute_normal = 0x00000080
    invalid_handle_value = ctypes.c_void_p(-1).value

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        path,
        generic_read,
        file_share_read | file_share_write | file_share_delete,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    if handle == invalid_handle_value:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return msvcrt.open_osfhandle(handle, flags | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        close_handle(handle)
        raise


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
        path = self._path_for(key)
        if os.name == "nt":
            return open(path, "rb", opener=_open_windows_reader_fd)
        return path.open("rb")

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        validate_storage_key(key)
        path = self.directory / key
        if path.resolve().parent != self.directory:
            raise ValueError("Storage key resolves outside the storage directory.")
        return path
