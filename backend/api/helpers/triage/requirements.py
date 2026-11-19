from ...agents.triage.schemas import TriageRequirement


def requirement_lines(
    requirements: list[TriageRequirement],
) -> list[str]:
    if not requirements:
        return []

    lines = ["Exigências identificadas:"]
    for requirement in requirements:
        lines.append(
            f"- {requirement.description} (fonte: {requirement.source})"
        )
    return lines
