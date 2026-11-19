from datetime import date

from .input import ConsultationInput
from .response import (
    CitedSource,
    ConsultationGapOrDivergence,
    ConsultationResponse,
)

INSUFFICIENT_SOURCES_MESSAGE = (
    "Não foram encontrados documentos ou registros na base consultada com "
    "dados suficientes para responder à pergunta."
)


def build_insufficient_sources_message(
    reference_date: date | str | None = None,
) -> str:
    if reference_date is None:
        return INSUFFICIENT_SOURCES_MESSAGE
    ref_iso = (
        reference_date.isoformat()
        if isinstance(reference_date, date)
        else str(reference_date)
    )
    return (
        f"Considerando a data de referência {ref_iso}: "
        f"{INSUFFICIENT_SOURCES_MESSAGE}"
    )


def reconcile_consultation_sources(
    response: ConsultationResponse,
    payload: ConsultationInput,
) -> ConsultationResponse:
    """Monta os metadados das citações a partir das fontes recuperadas e trata ausência de fontes."""
    resolved_date_iso = payload.resolved_reference_date.isoformat()

    if not payload.sources:
        return ConsultationResponse(
            answer=build_insufficient_sources_message(resolved_date_iso),
            reference_date_used=resolved_date_iso,
            source_ids=[],
            cited_sources=[],
            gaps_and_divergences=[
                ConsultationGapOrDivergence(
                    kind="lacuna",
                    description=(
                        "Nenhum trecho documental ou registro operacional foi "
                        "recuperado para a consulta."
                    ),
                    source_ids=[],
                )
            ],
            has_sufficient_data=False,
        )

    source_map = {item.source_id: item for item in payload.sources}
    valid_source_ids = [sid for sid in response.source_ids if sid in source_map]

    rebuilt_cited: list[CitedSource] = []
    cited_by_id = {
        c.source_id: c
        for c in response.cited_sources
        if c.source_id in source_map
    }

    for sid in valid_source_ids:
        origin = source_map[sid]
        existing = cited_by_id.get(sid)
        rebuilt_cited.append(
            CitedSource(
                source_id=sid,
                document_id=origin.document_id,
                document_name=origin.document_name,
                reference_label=origin.reference_label,
                supporting_excerpt=(
                    existing.supporting_excerpt if existing else None
                ),
            )
        )

    cleaned_gaps: list[ConsultationGapOrDivergence] = []
    for gap in response.gaps_and_divergences:
        filtered_gap_ids = [sid for sid in gap.source_ids if sid in source_map]
        cleaned_gaps.append(
            ConsultationGapOrDivergence(
                kind=gap.kind,
                description=gap.description,
                source_ids=filtered_gap_ids,
            )
        )

    return ConsultationResponse(
        answer=response.answer,
        reference_date_used=resolved_date_iso,
        source_ids=valid_source_ids,
        cited_sources=rebuilt_cited,
        gaps_and_divergences=cleaned_gaps,
        has_sufficient_data=response.has_sufficient_data,
    )


__all__ = [
    "INSUFFICIENT_SOURCES_MESSAGE",
    "build_insufficient_sources_message",
    "reconcile_consultation_sources",
]
