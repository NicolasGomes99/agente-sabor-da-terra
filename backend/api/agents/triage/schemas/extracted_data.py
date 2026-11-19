from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .input import _normalize_iso_date_str
from .items import TriageExtractedItem, TriageRequirement


class TriageExtractedData(BaseModel):
    buyer_name: str | None = Field(
        default=None,
        description="Nome do comprador, produtor ou instituição remetente.",
    )
    buyer_contact: str | None = Field(
        default=None,
        description="Telefone, e-mail ou pessoa de contato informada na mensagem.",
    )
    buyer_document: str | None = Field(
        default=None,
        description="CNPJ ou CPF mencionado na mensagem.",
    )
    delivery_date_start: str | None = Field(
        default=None,
        description=(
            "Data de entrega única ou data inicial do intervalo no formato "
            "AAAA-MM-DD, calculada a partir da data de recebimento."
        ),
    )
    delivery_date_end: str | None = Field(
        default=None,
        description=(
            "Data final no formato AAAA-MM-DD quando a entrega tiver um "
            "intervalo de datas."
        ),
    )
    delivery_reference_raw: str | None = Field(
        default=None,
        description="Expressão original de prazo presente na mensagem.",
    )
    has_date_conflict: bool = Field(
        default=False,
        description=(
            "True quando houver conflito entre data explícita, dia da semana "
            "ou outra referência de prazo."
        ),
    )
    date_conflict_description: str | None = Field(
        default=None,
        description="Explicação clara de quais referências de prazo entram em conflito.",
    )
    delivery_time_window: str | None = Field(
        default=None,
        description="Horário ou turno de entrega informado (ex.: 'pela manhã', '7h às 12h').",
    )
    delivery_location: str | None = Field(
        default=None,
        description="Endereço ou local de entrega informado.",
    )
    payment_terms: str | None = Field(
        default=None,
        description="Forma ou condição de pagamento mencionada.",
    )
    supply_frequency: str | None = Field(
        default=None,
        description="Frequência de fornecimento quando mencionada (ex.: semanal, mensal, única).",
    )
    contract_reference: str | None = Field(
        default=None,
        description="Referência a contrato citada na mensagem (ex.: 'Contrato nº 045/2026-PNAE').",
    )
    general_conditions: list[str] = Field(
        default_factory=list,
        description="Condições gerais de atendimento expressas na mensagem.",
    )
    items: list[TriageExtractedItem] = Field(
        default_factory=list,
        description="Itens de produtos extraídos da mensagem.",
    )
    requirements: list[TriageRequirement] = Field(
        default_factory=list,
        description="Exigências identificadas na mensagem ou em contrato citado.",
    )
    requested_documents_or_sensitive_data: list[str] = Field(
        default_factory=list,
        description=(
            "Documentos internos, certificações, fichas técnicas, dados "
            "pessoais ou dados bancários solicitados pelo remetente (RF37)."
        ),
    )

    @field_validator("delivery_date_start", "delivery_date_end", mode="before")
    @classmethod
    def _validate_iso_dates(cls, value: date | datetime | str | None) -> str | None:
        return _normalize_iso_date_str(value)

    @model_validator(mode="after")
    def _validate_date_range(self) -> "TriageExtractedData":
        start = self.delivery_start_as_date
        end = self.delivery_end_as_date
        if start is not None and end is not None and end < start:
            raise ValueError(
                "delivery_date_end must be greater than or equal to delivery_date_start."
            )
        return self

    @property
    def delivery_start_as_date(self) -> date | None:
        if self.delivery_date_start is None:
            return None
        return date.fromisoformat(self.delivery_date_start)

    @property
    def delivery_end_as_date(self) -> date | None:
        if self.delivery_date_end is None:
            return None
        return date.fromisoformat(self.delivery_date_end)
