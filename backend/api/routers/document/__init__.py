from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from ...dependencies import get_current_user, get_document_service
from ...models.document import Document
from ...schemas.document import DocumentResponse
from ...services.document import DocumentNotFoundError, DocumentService
from .stream import INLINE_MEDIA_TYPES, DocumentStreamResponse, file_responses
from .upload import document_upload

ERROR_DETAIL_CONTENT = {
    "application/json": {
        "schema": {
            "type": "object",
            "required": ["detail"],
            "properties": {"detail": {"type": "string"}},
        }
    }
}

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {
            "description": "A valid bearer token is required.",
            "content": ERROR_DETAIL_CONTENT,
            "headers": {
                "WWW-Authenticate": {"schema": {"type": "string", "example": "Bearer"}}
            },
        }
    },
)

DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]


@router.get("", response_model=list[DocumentResponse])
async def list_documents(service: DocumentServiceDependency) -> list[Document]:
    return await service.list_documents()


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"description": "Document upload exceeds the size limit."},
        422: {
            "description": "A document file with a filename is required.",
            "content": ERROR_DETAIL_CONTENT,
        },
    },
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
    async with document_upload(request) as (filename, source):
        return await service.create_document(filename, source)


async def _document_response(
    document_id: UUID, service: DocumentService, *, download: bool
) -> DocumentStreamResponse:
    try:
        filename, open_reader = await service.prepare_document_read(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found.") from error
    return DocumentStreamResponse(open_reader, filename, download=download)


@router.get(
    "/{document_id}/content",
    response_class=StreamingResponse,
    responses=file_responses([*sorted(INLINE_MEDIA_TYPES), "application/octet-stream"]),
)
async def open_document(
    document_id: UUID, service: DocumentServiceDependency
) -> DocumentStreamResponse:
    return await _document_response(document_id, service, download=False)


@router.get(
    "/{document_id}/download",
    response_class=StreamingResponse,
    responses=file_responses(["application/octet-stream"]),
)
async def download_document(
    document_id: UUID, service: DocumentServiceDependency
) -> DocumentStreamResponse:
    return await _document_response(document_id, service, download=True)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Document not found.", "content": ERROR_DETAIL_CONTENT}},
)
async def delete_document(document_id: UUID, service: DocumentServiceDependency) -> Response:
    try:
        await service.delete_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail="Document not found.") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
