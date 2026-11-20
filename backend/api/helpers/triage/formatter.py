from ...agents.triage.schemas import TriageAnalysis, TriageInput
from ...models.solicitation import SolicitationType, SolicitationUrgency
from .dates import format_date, format_text_dates
from .deadlines import deadline_lines
from .details import additional_intent_lines, contact_lines
from .documents import document_lines
from .items import item_lines
from .pending import pending_lines
from .requirements import requirement_lines

_TYPE_LABELS = {
    SolicitationType.ORDER: "Pedido",
    SolicitationType.CONSULTATION: "Consulta",
    SolicitationType.OFFER: "Oferta",
    SolicitationType.NOTICE: "Comunicado",
    SolicitationType.UNIDENTIFIED: "Não identificado",
}

_URGENCY_LABELS = {
    SolicitationUrgency.URGENT: "Urgente",
    SolicitationUrgency.NORMAL: "Normal",
    SolicitationUrgency.UNDETERMINED: "Indeterminada",
}


def build_triage_session_title(
    payload: TriageInput,
    analysis: TriageAnalysis,
) -> str:
    source = payload.source_id or analysis.summary
    return source[:120]


def format_triage_analysis(analysis: TriageAnalysis) -> str:
    request_type = SolicitationType(analysis.request_type.value)
    urgency = SolicitationUrgency(analysis.urgency.value)

    lines = [
        "Análise inicial da triagem",
        f"Resumo: {format_text_dates(analysis.summary)}",
        f"Tipo da intenção principal: {_TYPE_LABELS[request_type]}",
        f"Urgência: {_URGENCY_LABELS[urgency]}",
        f"Motivo da urgência: {format_text_dates(analysis.urgency_reason)}",
        (
            "Data de recebimento considerada: "
            f"{format_date(analysis.received_date_reference)}"
        ),
    ]
    lines.extend(additional_intent_lines(analysis))

    extracted = analysis.extracted_data
    lines.extend(contact_lines(extracted))
    lines.extend(deadline_lines(extracted.deadlines))
    lines.extend(item_lines(extracted.items))
    lines.extend(requirement_lines(extracted.requirements))
    lines.extend(document_lines(extracted))
    lines.extend(pending_lines(analysis.pending_items))
    if analysis.document_enrichment and analysis.document_enrichment.findings:
        lines.append("Verificação documental e operacional:")
        for finding in analysis.document_enrichment.findings:
            follow_up = " [a verificar]" if finding.needs_follow_up else ""
            lines.append(f"- {finding.description}{follow_up}")
    return "\n".join(lines)
