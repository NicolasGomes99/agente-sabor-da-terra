from ...agents.triage.schemas import (
    TriageAnalysis,
    TriageExtractedData,
)


def additional_intent_lines(analysis: TriageAnalysis) -> list[str]:
    if not analysis.additional_intents:
        return []
    return ["Intenções adicionais: " + "; ".join(analysis.additional_intents)]


def contact_lines(extracted: TriageExtractedData) -> list[str]:
    lines = []
    if extracted.buyer_name:
        lines.append(f"Comprador ou remetente: {extracted.buyer_name}")
    if extracted.buyer_contact:
        lines.append(f"Contato: {extracted.buyer_contact}")
    return lines
