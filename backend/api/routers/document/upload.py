from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import BinaryIO

from fastapi import HTTPException, Request, status
from starlette.datastructures import UploadFile
from starlette.types import Message

from ...config import get_document_upload_max_bytes


def _upload_too_large() -> HTTPException:
    return HTTPException(status_code=413, detail="Document upload exceeds the size limit.")


def _limit_upload(request: Request, limit: int) -> Request:
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isascii() and content_length.isdecimal():
        digits = content_length.lstrip("0")
        maximum = str(limit)
        if len(digits) > len(maximum) or (
            len(digits) == len(maximum) and digits > maximum
        ):
            raise _upload_too_large()

    received = 0

    async def receive() -> Message:
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise _upload_too_large()
        return message

    return Request(request.scope, receive=receive)


@asynccontextmanager
async def document_upload(request: Request) -> AsyncIterator[tuple[str, BinaryIO]]:
    upload_request = _limit_upload(request, get_document_upload_max_bytes())
    async with upload_request.form() as form:
        file = form.get("file")
        if not isinstance(file, UploadFile) or not file.filename or not file.filename.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A document file with a filename is required.",
            )
        yield file.filename, file.file
