from ...agents.triage.schemas import TriagePendingItem
from .dates import format_text_dates


def pending_lines(pending_items: list[TriagePendingItem]) -> list[str]:
    lines = ["Pendências:"]
    if not pending_items:
        lines.append("- Nenhuma pendência identificada.")
        return lines

    for pending in pending_items:
        lines.append(
            f"- {format_text_dates(pending.description)} "
            "Pergunta ao funcionário: "
            f"{format_text_dates(pending.question_for_staff)}"
        )
    return lines
