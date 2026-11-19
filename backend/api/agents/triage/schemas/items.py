from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
