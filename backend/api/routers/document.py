from collections.abc import AsyncIterator
from mimetypes import guess_type
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from anyio import CancelScope
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile
from starlette.types import Message, Receive, Scope, Send

from ..config import get_document_upload_max_bytes
from ..dependencies import get_current_user, get_document_service
from ..models.document import Document
from ..schemas.document import DocumentResponse
from ..services.document import DocumentNotFoundError, DocumentService
from ..storage.base import DocumentReader

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)]
)

DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]
INLINE_MEDIA_TYPES = {"application/pdf", "image/gif", "image/jpeg", "image/png", "image/webp"}
READ_SIZE = 64 * 1024


class DocumentStreamResponse(StreamingResponse):
    def __init__(self, reader: DocumentReader, filename: str, *, download: bool) -> None:
        self.reader = reader
        media_type, _ = guess_type(filename)
        inline = not download and media_type in INLINE_MEDIA_TYPES
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


@router.get("", response_model=list[DocumentResponse])
async def list_documents(service: DocumentServiceDependency) -> list[Document]:
    return await service.list_documents()


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


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={413: {"description": "Document upload exceeds the size limit."}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def create_document(
    request: Request, service: DocumentServiceDependency
) -> Document:
    upload_request = _limit_upload(request, get_document_upload_max_bytes())
    async with upload_request.form() as form:
        file = form.get("file")
        if not isinstance(file, UploadFile) or not file.filename or not file.filename.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A document file with a filename is required.",
            )
        return await service.create_document(file.filename, file.file)


async def _document_response(
    document_id: UUID, service: DocumentService, *, download: bool
) -> DocumentStreamResponse:
    try:
        filename, reader = await service.open_document(document_id)
    except (DocumentNotFoundError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail="Document not found.") from error
    return DocumentStreamResponse(reader, filename, download=download)


@router.get("/{document_id}/content", response_class=StreamingResponse)
async def open_document(
    document_id: UUID, service: DocumentServiceDependency
) -> DocumentStreamResponse:
    return await _document_response(document_id, service, download=False)


@router.get("/{document_id}/download", response_class=StreamingResponse)
async def download_document(
    document_id: UUID, service: DocumentServiceDependency
) -> DocumentStreamResponse:
    return await _document_response(document_id, service, download=True)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, service: DocumentServiceDependency) -> Response:
    try:
        await service.delete_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found.") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
