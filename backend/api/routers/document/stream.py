from asyncio import CancelledError, create_task, shield, to_thread, wait
from collections.abc import AsyncIterator, Callable, Coroutine
from mimetypes import guess_type
from typing import Any
from urllib.parse import quote

from anyio import CancelScope
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from ...storage.base import DocumentReader

INLINE_MEDIA_TYPES = {"application/pdf", "image/gif", "image/jpeg", "image/png", "image/webp"}
READ_SIZE = 64 * 1024


def file_responses(media_types: list[str]) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": "Document file.",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in media_types
            },
            "headers": {
                "Content-Disposition": {
                    "description": "Disposition and original filename.",
                    "schema": {"type": "string"},
                }
            },
        },
        404: {"description": "Document or stored file not found."},
    }


async def _finish_reader_operation[T](operation: Coroutine[object, object, T]) -> T:
    task = create_task(operation)
    try:
        return await shield(task)
    except CancelledError:
        # A running worker cannot be interrupted safely by closing its reader.
        with CancelScope(shield=True):
            while not task.done():
                try:
                    await wait((task,))
                except CancelledError:
                    continue
        if not task.cancelled():
            task.exception()
        raise


class DocumentStreamResponse(StreamingResponse):
    def __init__(
        self, open_reader: Callable[[], DocumentReader], filename: str, *, download: bool
    ) -> None:
        self._open_reader = open_reader
        self._reader: DocumentReader | None = None
        media_type, encoding = guess_type(filename)
        inline = not download and encoding is None and media_type in INLINE_MEDIA_TYPES
        disposition = "inline" if inline else "attachment"
        super().__init__(
            self._read_chunks(),
            media_type=media_type if inline else "application/octet-stream",
            headers={
                "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def _read_chunks(self) -> AsyncIterator[bytes]:
        reader = self._reader
        assert reader is not None
        while chunk := await _finish_reader_operation(to_thread(reader.read, READ_SIZE)):
            yield chunk

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def acquire_reader() -> None:
            self._reader = await to_thread(self._open_reader)

        try:
            try:
                await _finish_reader_operation(acquire_reader())
            except FileNotFoundError as error:
                raise HTTPException(status_code=404, detail="Document not found.") from error
            await super().__call__(scope, receive, send)
        finally:
            if self._reader is not None:
                with CancelScope(shield=True):
                    await _finish_reader_operation(to_thread(self._reader.close))
