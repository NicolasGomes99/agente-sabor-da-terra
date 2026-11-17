from collections.abc import AsyncIterator
from mimetypes import guess_type
from typing import Any
from urllib.parse import quote

from anyio import CancelScope
from fastapi.concurrency import run_in_threadpool
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


class DocumentStreamResponse(StreamingResponse):
    def __init__(self, reader: DocumentReader, filename: str, *, download: bool) -> None:
        self.reader = reader
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
        while chunk := await run_in_threadpool(self.reader.read, READ_SIZE):
            yield chunk

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await run_in_threadpool(self.reader.close)
