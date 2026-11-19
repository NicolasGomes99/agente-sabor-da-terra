from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .input import _normalize_iso_date_str


class DeadlineAction(StrEnum):
    DELIVERY = "entrega"
    RESPONSE = "resposta"
    DOCUMENT_AVAILABILITY = "disponibilizacao_de_documentos"


class TriageDeadline(BaseModel):
    action: DeadlineAction = Field(
        description=(
            "Ação solicitada associada ao prazo: 'entrega', 'resposta' "
            "ou 'disponibilizacao_de_documentos'."
        ),
    )
    date_start: str | None = Field(
        default=None,
        description=(
            "Data única ou primeiro dia do período/intervalo no formato AAAA-MM-DD."
        ),
    )
    date_end: str | None = Field(
        default=None,
        description=(
            "Último dia no formato AAAA-MM-DD quando o prazo for um intervalo ou período."
        ),
    )
    reference_raw: str | None = Field(
        default=None,
        description="Expressão original do prazo presente na mensagem.",
    )
    has_conflict: bool = Field(
        default=False,
        description="True quando houver conflito entre as referências de data deste prazo.",
    )
    conflict_description: str | None = Field(
        default=None,
        description="Descrição das referências conflitantes deste prazo, quando houver.",
    )

    @field_validator("date_start", "date_end", mode="before")
    @classmethod
    def _validate_iso_dates(cls, value: date | datetime | str | None) -> str | None:
        return _normalize_iso_date_str(value)

    @model_validator(mode="after")
    def _validate_date_range(self) -> "TriageDeadline":
        start = self.start_as_date
        end = self.end_as_date
        if start is not None and end is not None and end < start:
            raise ValueError("date_end must be greater than or equal to date_start.")
        return self

    @property
    def start_as_date(self) -> date | None:
        if self.date_start is None:
            return None
        return date.fromisoformat(self.date_start)

    @property
    def end_as_date(self) -> date | None:
        if self.date_end is None:
            return None
        return date.fromisoformat(self.date_end)


class TriageExtractedItem(BaseModel):
    product: str = Field(
        min_length=1,
        description=(
            "Nome do produto em português (traduzido quando a mensagem estiver "
            "em outro idioma)."
        ),
    )
    original_mention: str | None = Field(
        default=None,
        description="Trecho ou termo original usado na mensagem para o item.",
    )
    quantity: float | None = Field(
        default=None,
        description=(
            "Quantidade numérica individual do item (> 0), quando definida sem "
            "agregação com outros produtos."
        ),
    )
    quantity_raw: str | None = Field(
        default=None,
        description="Descrição textual original da quantidade (ex.: 'uns 15kg', '100kg total').",
    )
    unit: str | None = Field(
        default=None,
        description="Unidade informada na mensagem, preservada sem conversão indevida.",
    )
    conditional: bool = Field(
        default=False,
        description="True quando o item foi solicitado sob condição (ex.: 'se tiver').",
    )
    condition_text: str | None = Field(
        default=None,
        description="Condição específica associada ao item (ex.: 'se tiver', 'orgânico').",
    )
    ambiguous_or_aggregate: bool = Field(
        default=False,
        description=(
            "True quando a quantidade é agregada entre vários produtos, "
            "ambígua/aproximada ou o produto é indefinido."
        ),
    )
    clarification_needed: str | None = Field(
        default=None,
        description="Informação específica que falta confirmar sobre este item.",
    )

    @field_validator("quantity")
    @classmethod
    def _validate_positive_quantity(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("quantity must be greater than zero.")
        return value


class TriageRequirement(BaseModel):
    description: str = Field(
        min_length=1,
        description="Descrição em português da exigência identificada.",
    )
    source: Literal["mensagem", "contrato", "ambos"] = Field(
        default="mensagem",
        description="Origem da exigência conforme RF03 e RF06.",
    )
    contract_reference: str | None = Field(
        default=None,
        description="Identificação do contrato citado na mensagem, quando houver.",
    )
    verification_needed: str | None = Field(
        default=None,
        description="O que o funcionário ainda precisa conferir para atender à exigência.",
    )
