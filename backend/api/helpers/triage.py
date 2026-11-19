import re
from datetime import date

from ..agents.triage.schemas import (
    TriageAnalysis,
    TriageExtractedData,
    TriageExtractedItem,
    TriageInput,
    TriagePendingItem,
    TriageRequirement,
)
from ..models.solicitation import SolicitationType, SolicitationUrgency

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

_DEADLINE_ACTIONS = {
    SolicitationType.ORDER: "Entregar",
    SolicitationType.CONSULTATION: "Responder à consulta",
    SolicitationType.OFFER: "Responder ao produtor",
    SolicitationType.NOTICE: "Cumprir a providência",
    SolicitationType.UNIDENTIFIED: "Verificar o prazo",
}


def _format_text_dates(value: str) -> str:
    return re.sub(
        r"\b(\d{4})-(\d{2})-(\d{2})\b",
        lambda match: f"{match.group(3)}/{match.group(2)}/{match.group(1)}",
        value,
    )


def _format_date(value: date | str | None) -> str:
    if value is None:
        return "não informada"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d/%m/%Y")


def _format_quantity(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return str(value).replace(".", ",")


def build_triage_session_title(
    payload: TriageInput,
    analysis: TriageAnalysis,
) -> str:
    source = payload.source_id or analysis.summary
    return source[:120]


def _additional_intent_lines(analysis: TriageAnalysis) -> list[str]:
    if not analysis.additional_intents:
        return []
    return [
        "Intenções adicionais: " + "; ".join(analysis.additional_intents)
    ]


def _contact_lines(extracted: TriageExtractedData) -> list[str]:
    lines = []
    if extracted.buyer_name:
        lines.append(f"Comprador ou remetente: {extracted.buyer_name}")
    if extracted.buyer_contact:
        lines.append(f"Contato: {extracted.buyer_contact}")
    return lines


def _deadline_lines(
    extracted: TriageExtractedData,
    request_type: SolicitationType,
) -> list[str]:
    delivery_start = extracted.delivery_start_as_date
    delivery_end = extracted.delivery_end_as_date

    if delivery_start is None:
        lines = ["Prazo: não informado na análise."]
    else:
        if delivery_end is not None and delivery_end != delivery_start:
            deadline = (
                f"{_format_date(delivery_start)} a "
                f"{_format_date(delivery_end)}"
            )
        else:
            deadline = _format_date(delivery_start)
        lines = [
            f"Ação: {_DEADLINE_ACTIONS[request_type]}",
            f"Prazo: {deadline}",
        ]

    if extracted.delivery_reference_raw:
        lines.append(
            "Referência original do prazo: "
            f"{extracted.delivery_reference_raw}"
        )
    return lines


def _item_lines(items: list[TriageExtractedItem]) -> list[str]:
    if not items:
        return []

    lines = ["Itens identificados:"]
    for item in items:
        quantity = _format_quantity(item.quantity)
        unit = f" {item.unit}" if item.unit else ""
        details = f"{quantity}{unit}".strip()
        condition = (
            f" (condição: {item.condition_text})"
            if item.condition_text
            else ""
        )
        lines.append(
            f"- {item.product}: {details or 'quantidade a confirmar'}"
            f"{condition}"
        )
    return lines


def _requirement_lines(
    requirements: list[TriageRequirement],
) -> list[str]:
    if not requirements:
        return []

    lines = ["Exigências identificadas:"]
    for requirement in requirements:
        lines.append(
            f"- {requirement.description} "
            f"(fonte: {requirement.source})"
        )
    return lines


def _document_lines(extracted: TriageExtractedData) -> list[str]:
    if not extracted.requested_documents_or_sensitive_data:
        return []
    return [
        "Documentos ou dados solicitados: "
        + "; ".join(extracted.requested_documents_or_sensitive_data)
    ]


def _pending_lines(pending_items: list[TriagePendingItem]) -> list[str]:
    lines = ["Pendências:"]
    if not pending_items:
        lines.append("- Nenhuma pendência identificada.")
        return lines

    for pending in pending_items:
        lines.append(
            f"- {_format_text_dates(pending.description)} "
            "Pergunta ao funcionário: "
            f"{_format_text_dates(pending.question_for_staff)}"
        )
    return lines


def format_triage_analysis(analysis: TriageAnalysis) -> str:
    request_type = SolicitationType(analysis.request_type.value)
    urgency = SolicitationUrgency(analysis.urgency.value)

    lines = [
        "Análise inicial da triagem",
        f"Resumo: {_format_text_dates(analysis.summary)}",
        f"Tipo da intenção principal: {_TYPE_LABELS[request_type]}",
        f"Urgência: {_URGENCY_LABELS[urgency]}",
        (
            "Motivo da urgência: "
            f"{_format_text_dates(analysis.urgency_reason)}"
        ),
        (
            "Data de recebimento considerada: "
            f"{_format_date(analysis.received_date_reference)}"
        ),
    ]
    lines.extend(_additional_intent_lines(analysis))

    extracted = analysis.extracted_data
    lines.extend(_contact_lines(extracted))
    lines.extend(_deadline_lines(extracted, request_type))
    lines.extend(_item_lines(extracted.items))
    lines.extend(_requirement_lines(extracted.requirements))
    lines.extend(_document_lines(extracted))
    lines.extend(_pending_lines(analysis.pending_items))
    return "\n".join(lines)
