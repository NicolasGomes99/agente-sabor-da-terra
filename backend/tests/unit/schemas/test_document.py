from uuid import uuid4

from api.models.document import Document
from api.schemas.document import DocumentResponse


def test_document_response_serializes_model_attributes() -> None:
    document_id = uuid4()
    document = Document(
        id=document_id,
        original_filename="certificado.pdf",
        storage_key="internal-key",
    )

    response = DocumentResponse.model_validate(document)

    assert response.model_dump(mode="json") == {
        "id": str(document_id),
        "original_filename": "certificado.pdf",
    }
