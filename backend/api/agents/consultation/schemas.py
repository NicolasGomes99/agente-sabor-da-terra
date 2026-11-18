from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import PERNAMBUCO_TIMEZONE, to_pernambuco_date


class SourceKind(StrEnum):
    DOCUMENT_CHUNK = "trecho_documento"
    LOT_RECORD = "registro_lote"
    PRODUCER_RECORD = "registro_produtor"
    OTHER_RECORD = "outro_registro"


def _normalize_iso_date_str(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return to_pernambuco_date(value).isoformat()


class ConsultationSourceItem(BaseModel):
    source_id: str = Field(
        min_length=1,
        description=(
            "Identificador único do trecho documental (ex.: UUID de "
            "TrechoDocumento) ou do registro recuperado."
        ),
    )
    source_kind: SourceKind = Field(
        default=SourceKind.DOCUMENT_CHUNK,
        description="Tipo da fonte recuperada.",
    )
    document_id: str | None = Field(
        default=None,
        description="Identificador do documento original, quando disponível.",
    )
    document_name: str = Field(
        min_length=1,
        description="Nome do documento ou arquivo de origem.",
    )
    reference_label: str | None = Field(
        default=None,
        description=(
            "Identificador de negócio do registro ou seção (ex.: 'LOT-2026-0094', "
            "'ORG-PE-2025-003198', 'Cláusula 4')."
        ),
    )
    content: str = Field(
        min_length=1,
        description="Conteúdo textual do trecho ou dos campos do registro.",
    )

    @field_validator("source_id", "document_name", "content")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank.")
        return stripped


class ConsultationInput(BaseModel):
    question: str = Field(
        min_length=1,
        description="Pergunta do funcionário no chat.",
    )
    reference_date: datetime | date | str | None = Field(
        default=None,
        description=(
            "Data de referência da consulta. Quando omitida, usa a data atual "
            "no fuso de Pernambuco."
        ),
    )
    sources: list[ConsultationSourceItem] = Field(
        default_factory=list,
        description="Trechos documentais e registros recuperados para a consulta.",
    )

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank.")
        return stripped

    @field_validator("reference_date")
    @classmethod
    def _validate_reference_date(
        cls,
        value: datetime | date | str | None,
    ) -> datetime | date | str | None:
        if value is not None:
            to_pernambuco_date(value)
        return value

    @property
    def resolved_reference_date(self) -> date:
        if self.reference_date is not None:
            return to_pernambuco_date(self.reference_date)
        return datetime.now(PERNAMBUCO_TIMEZONE).date()


class CitedSource(BaseModel):
    source_id: str = Field(
        min_length=1,
        description="Identificador da fonte recuperada que sustenta a informação.",
    )
    document_id: str | None = Field(
        default=None,
        description="Identificador do documento original, quando disponível.",
    )
    document_name: str = Field(
        min_length=1,
        description="Nome do documento ou arquivo citado.",
    )
    reference_label: str | None = Field(
        default=None,
        description="Registro, lote, certificado ou seção pertinente dentro da fonte.",
    )
    supporting_excerpt: str | None = Field(
        default=None,
        description="Resumo ou trecho da evidência utilizada na resposta.",
    )


class ConsultationGapOrDivergence(BaseModel):
    kind: Literal[
        "lacuna",
        "divergencia",
        "unidade_ambigua",
        "certificacao_vencida_ou_incompativel",
    ] = Field(
        description="Tipo de apontamento identificado nos dados consultados.",
    )
    description: str = Field(
        min_length=1,
        description="Explicação clara em português da lacuna, divergência ou pendência.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores das fontes relacionadas ao apontamento.",
    )


class ConsultationResponse(BaseModel):
    answer: str = Field(
        min_length=1,
        description=(
            "Texto da resposta em português para exibição no chat, indicando a "
            "data de referência e as fontes."
        ),
    )
    reference_date_used: str = Field(
        description="Data de referência usada na análise no formato AAAA-MM-DD.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Lista ordenada e sem duplicatas dos identificadores (source_id) "
            "das fontes que sustentam a resposta."
        ),
    )
    cited_sources: list[CitedSource] = Field(
        default_factory=list,
        description="Detalhamento das fontes utilizadas na resposta.",
    )
    gaps_and_divergences: list[ConsultationGapOrDivergence] = Field(
        default_factory=list,
        description="Lacunas, divergências entre fontes, unidades ambíguas ou restrições.",
    )
    has_sufficient_data: bool = Field(
        default=True,
        description=(
            "False quando os trechos e registros fornecidos estão ausentes ou "
            "são insuficientes para responder à pergunta."
        ),
    )

    @field_validator("answer")
    @classmethod
    def _validate_answer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer must not be blank.")
        return stripped

    @field_validator("reference_date_used", mode="before")
    @classmethod
    def _validate_reference_date_used(cls, value: date | datetime | str) -> str:
        normalized = _normalize_iso_date_str(value)
        if normalized is None:
            raise ValueError("reference_date_used is required.")
        return normalized

    @property
    def reference_date(self) -> date:
        return date.fromisoformat(self.reference_date_used)

    @model_validator(mode="after")
    def _deduplicate_and_sync_sources(self) -> "ConsultationResponse":
        ordered_ids: list[str] = []
        seen: set[str] = set()

        for sid in self.source_ids:
            cleaned = sid.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered_ids.append(cleaned)

        for cited in self.cited_sources:
            cleaned = cited.source_id.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered_ids.append(cleaned)

        self.source_ids = ordered_ids
        return self


def reconcile_consultation_sources(
    response: ConsultationResponse,
    payload: ConsultationInput,
) -> ConsultationResponse:
    """Garante que apenas fontes fornecidas na entrada sejam citadas e completa metadados."""
    source_map = {item.source_id: item for item in payload.sources}
    resolved_date_iso = payload.resolved_reference_date.isoformat()

    valid_source_ids = [sid for sid in response.source_ids if sid in source_map]

    rebuilt_cited: list[CitedSource] = []
    cited_by_id = {c.source_id: c for c in response.cited_sources if c.source_id in source_map}

    for sid in valid_source_ids:
        origin = source_map[sid]
        existing = cited_by_id.get(sid)
        rebuilt_cited.append(
            CitedSource(
                source_id=sid,
                document_id=(existing.document_id if existing and existing.document_id else origin.document_id),
                document_name=origin.document_name,
                reference_label=(
                    existing.reference_label
                    if existing and existing.reference_label
                    else origin.reference_label
                ),
                supporting_excerpt=existing.supporting_excerpt if existing else None,
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

    has_sufficient = response.has_sufficient_data and bool(payload.sources)
    if not payload.sources and not any(g.kind == "lacuna" for g in cleaned_gaps):
        cleaned_gaps.append(
            ConsultationGapOrDivergence(
                kind="lacuna",
                description=(
                    "Nenhum trecho documental ou registro operacional foi "
                    "recuperado para a consulta."
                ),
                source_ids=[],
            )
        )

    return ConsultationResponse(
        answer=response.answer,
        reference_date_used=resolved_date_iso,
        source_ids=valid_source_ids,
        cited_sources=rebuilt_cited,
        gaps_and_divergences=cleaned_gaps,
        has_sufficient_data=has_sufficient,
    )
