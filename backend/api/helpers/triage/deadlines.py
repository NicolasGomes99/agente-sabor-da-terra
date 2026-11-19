from ...agents.triage.schemas import TriageDeadline
from ...agents.triage.schemas.items import DeadlineAction
from .dates import format_date

_ACTION_LABELS = {
    DeadlineAction.DELIVERY: "Entregar",
    DeadlineAction.RESPONSE: "Responder",
    DeadlineAction.DOCUMENT_AVAILABILITY: "Disponibilizar documentos",
}


def deadline_lines(deadlines: list[TriageDeadline]) -> list[str]:
    if not deadlines:
        return ["Prazo: não informado na análise."]

    lines: list[str] = []
    for deadline in deadlines:
        start = deadline.start_as_date
        end = deadline.end_as_date
        if start is None:
            if deadline.has_conflict:
                date_text = "não determinado (referências em conflito)"
            else:
                date_text = "não informado"
        elif end is not None and end != start:
            date_text = f"{format_date(start)} a {format_date(end)}"
        else:
            date_text = format_date(start)

        if deadline.has_conflict and start is not None:
            date_text += " (em conflito)"

        lines.extend(
            [
                f"Ação: {_ACTION_LABELS[deadline.action]}",
                f"Prazo: {date_text}",
            ]
        )
        if deadline.reference_raw:
            lines.append(
                f"Referência original do prazo: {deadline.reference_raw}"
            )
        if deadline.conflict_description:
            lines.append(
                f"Conflito no prazo: {deadline.conflict_description}"
            )
    return lines
