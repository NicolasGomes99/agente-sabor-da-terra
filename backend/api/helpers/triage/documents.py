from ...agents.triage.schemas import TriageExtractedData


def document_lines(extracted: TriageExtractedData) -> list[str]:
    if not extracted.requested_documents_or_sensitive_data:
        return []
    return [
        "Documentos ou dados solicitados: "
        + "; ".join(extracted.requested_documents_or_sensitive_data)
    ]
