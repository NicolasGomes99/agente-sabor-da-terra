import re
from datetime import date


def format_text_dates(value: str) -> str:
    return re.sub(
        r"\b(\d{4})-(\d{2})-(\d{2})\b",
        lambda match: f"{match.group(3)}/{match.group(2)}/{match.group(1)}",
        value,
    )


def format_date(value: date | str | None) -> str:
    if value is None:
        return "não informada"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d/%m/%Y")


def format_quantity(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return str(value).replace(".", ",")
