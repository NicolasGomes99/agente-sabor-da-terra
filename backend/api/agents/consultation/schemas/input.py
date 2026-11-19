from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ...config import PERNAMBUCO_TIMEZONE, to_pernambuco_date


class SourceKind(StrEnum):
    DOCUMENT_CHUNK = "trecho_documento"
    LOT_RECORD = "registro_lote"
    PRODUCER_RECORD = "registro_produtor"
    FINANCIAL_RECORD = "registro_financeiro"
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
            "'FIN-2026-006', 'ORG-PE-2025-003198', 'Cláusula 4')."
        ),
    )
    record_id: str | None = Field(
        default=None,
        description="Identificador da linha quando a fonte é um registro de CSV no RAG.",
    )
    record_fields: dict[str, Any] | None = Field(
        default=None,
        description="Campos consultáveis da linha do CSV indexada no RAG.",
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

    @model_validator(mode="after")
    def _sync_record_id_and_reference_label(self) -> "ConsultationSourceItem":
        if self.reference_label is None and self.record_id:
            self.reference_label = self.record_id
        elif self.record_id is None and self.reference_label:
            self.record_id = self.reference_label
        return self


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
    producer_id: str | None = Field(
        default=None,
        description="Identificador ou nome do produtor quando a consulta solicita resumo financeiro.",
    )
    period_start: datetime | date | str | None = Field(
        default=None,
        description="Data inicial do período solicitado para o resumo financeiro.",
    )
    period_end: datetime | date | str | None = Field(
        default=None,
        description="Data final do período solicitado para o resumo financeiro.",
    )

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank.")
        return stripped

    @field_validator("reference_date", "period_start", "period_end")
    @classmethod
    def _validate_optional_dates(
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
