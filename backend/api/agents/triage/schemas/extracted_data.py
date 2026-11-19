from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .input import _normalize_iso_date_str
from .items import (
    DeadlineAction,
    TriageDeadline,
    TriageExtractedItem,
    TriageRequirement,
)


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
            "AAAA-MM-DD, preenchida apenas quando houver prazo de entrega."
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
        description="Expressão original do prazo de entrega presente na mensagem.",
    )
    has_date_conflict: bool = Field(
        default=False,
        description=(
            "True quando houver conflito entre data explícita, dia da semana "
            "ou outra referência de prazo de entrega."
        ),
    )
    date_conflict_description: str | None = Field(
        default=None,
        description="Explicação clara de quais referências de prazo entram em conflito.",
    )
    response_deadline: str | None = Field(
        default=None,
        description=(
            "Data limite de resposta ou retorno solicitada na mensagem (AAAA-MM-DD). "
            "Não deve ser gravada em delivery_date_start."
        ),
    )
    response_deadline_raw: str | None = Field(
        default=None,
        description="Expressão original do prazo de resposta (ex.: 'me avisa até amanhã').",
    )
    document_availability_date_start: str | None = Field(
        default=None,
        description=(
            "Data única ou primeiro dia do período em que documentos devem estar "
            "disponíveis (AAAA-MM-DD). Não deve ser gravada em delivery_date_start."
        ),
    )
    document_availability_date_end: str | None = Field(
        default=None,
        description=(
            "Último dia do período de disponibilização de documentos (AAAA-MM-DD), "
            "quando houver intervalo."
        ),
    )
    document_availability_raw: str | None = Field(
        default=None,
        description="Expressão original do prazo de disponibilização de documentos.",
    )
    deadlines: list[TriageDeadline] = Field(
        default_factory=list,
        description=(
            "Prazos identificados na mensagem, distinguindo entrega, resposta e "
            "disponibilização de documentos."
        ),
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

    @field_validator(
        "delivery_date_start",
        "delivery_date_end",
        "response_deadline",
        "document_availability_date_start",
        "document_availability_date_end",
        mode="before",
    )
    @classmethod
    def _validate_iso_dates(cls, value: date | datetime | str | None) -> str | None:
        return _normalize_iso_date_str(value)

    @model_validator(mode="after")
    def _validate_and_sync_deadlines(self) -> "TriageExtractedData":
        if (
            self.delivery_start_as_date is not None
            and self.delivery_end_as_date is not None
            and self.delivery_end_as_date < self.delivery_start_as_date
        ):
            raise ValueError(
                "delivery_date_end must be greater than or equal to delivery_date_start."
            )
        if (
            self.document_availability_start_as_date is not None
            and self.document_availability_end_as_date is not None
            and self.document_availability_end_as_date < self.document_availability_start_as_date
        ):
            raise ValueError(
                "document_availability_date_end must be greater than or equal to "
                "document_availability_date_start."
            )

        by_action: dict[DeadlineAction, TriageDeadline] = {
            d.action: d for d in self.deadlines
        }

        if DeadlineAction.DELIVERY in by_action:
            dl = by_action[DeadlineAction.DELIVERY]
            if self.delivery_date_start is None and dl.date_start is not None:
                self.delivery_date_start = dl.date_start
            if self.delivery_date_end is None and dl.date_end is not None:
                self.delivery_date_end = dl.date_end
            if self.delivery_reference_raw is None and dl.reference_raw is not None:
                self.delivery_reference_raw = dl.reference_raw
            if dl.has_conflict:
                self.has_date_conflict = True
                if not self.date_conflict_description and dl.conflict_description:
                    self.date_conflict_description = dl.conflict_description
        elif self.delivery_date_start is not None or self.has_date_conflict:
            self.deadlines.append(
                TriageDeadline(
                    action=DeadlineAction.DELIVERY,
                    date_start=self.delivery_date_start,
                    date_end=self.delivery_date_end,
                    reference_raw=self.delivery_reference_raw,
                    has_conflict=self.has_date_conflict,
                    conflict_description=self.date_conflict_description,
                )
            )

        if DeadlineAction.RESPONSE in by_action:
            dl = by_action[DeadlineAction.RESPONSE]
            if self.response_deadline is None and dl.date_start is not None:
                self.response_deadline = dl.date_start
            if self.response_deadline_raw is None and dl.reference_raw is not None:
                self.response_deadline_raw = dl.reference_raw
        elif self.response_deadline is not None:
            self.deadlines.append(
                TriageDeadline(
                    action=DeadlineAction.RESPONSE,
                    date_start=self.response_deadline,
                    reference_raw=self.response_deadline_raw,
                )
            )

        if DeadlineAction.DOCUMENT_AVAILABILITY in by_action:
            dl = by_action[DeadlineAction.DOCUMENT_AVAILABILITY]
            if self.document_availability_date_start is None and dl.date_start is not None:
                self.document_availability_date_start = dl.date_start
            if self.document_availability_date_end is None and dl.date_end is not None:
                self.document_availability_date_end = dl.date_end
            if self.document_availability_raw is None and dl.reference_raw is not None:
                self.document_availability_raw = dl.reference_raw
        elif self.document_availability_date_start is not None:
            self.deadlines.append(
                TriageDeadline(
                    action=DeadlineAction.DOCUMENT_AVAILABILITY,
                    date_start=self.document_availability_date_start,
                    date_end=self.document_availability_date_end,
                    reference_raw=self.document_availability_raw,
                )
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

    @property
    def response_deadline_as_date(self) -> date | None:
        if self.response_deadline is None:
            return None
        return date.fromisoformat(self.response_deadline)

    @property
    def document_availability_start_as_date(self) -> date | None:
        if self.document_availability_date_start is None:
            return None
        return date.fromisoformat(self.document_availability_date_start)

    @property
    def document_availability_end_as_date(self) -> date | None:
        if self.document_availability_date_end is None:
            return None
        return date.fromisoformat(self.document_availability_date_end)
