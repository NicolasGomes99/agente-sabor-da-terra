from ...agents.triage.schemas import TriageExtractedItem
from .dates import format_quantity


def item_lines(items: list[TriageExtractedItem]) -> list[str]:
    if not items:
        return []

    lines = ["Itens identificados:"]
    for item in items:
        quantity = format_quantity(item.quantity)
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
