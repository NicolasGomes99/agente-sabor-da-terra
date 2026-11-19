from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .input import _normalize_iso_date_str
from .items import (
    DeadlineAction,
    TriageDeadline,
    TriageExtractedItem,
    TriageRequirement,
)

_CANONICAL_ACTION_ORDER: tuple[DeadlineAction, ...] = (
    DeadlineAction.DELIVERY,
    DeadlineAction.RESPONSE,
    DeadlineAction.DOCUMENT_AVAILABILITY,
)


def _consolidate_action_entries(
    action: DeadlineAction,
    entries: list[TriageDeadline],
) -> TriageDeadline:
    if len(entries) == 1:
        return entries[0]

    distinct_ranges = {
        (e.date_start, e.date_end)
        for e in entries
        if e.date_start is not None or e.date_end is not None
    }
    raw_ref = next((e.reference_raw for e in entries if e.reference_raw), None)
    conflict_desc = next(
        (e.conflict_description for e in entries if e.conflict_description),
        None,
    )
    has_conflict = any(e.has_conflict for e in entries)

    if len(distinct_ranges) > 1:
        dates_text = ", ".join(
            sorted(d for pair in distinct_ranges for d in pair if d is not None)
        )
        return TriageDeadline(
            action=action,
            date_start=None,
            date_end=None,
            reference_raw=raw_ref,
            has_conflict=True,
            conflict_description=(
                conflict_desc
                or f"Datas divergentes informadas para {action.value}: {dates_text}."
            ),
        )

    date_start, date_end = next(iter(distinct_ranges), (None, None))
    return TriageDeadline(
        action=action,
        date_start=date_start,
        date_end=date_end,
        reference_raw=raw_ref,
        has_conflict=has_conflict,
        conflict_description=conflict_desc,
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
            "AAAA-MM-DD, sincronizada com o prazo de 'entrega' em deadlines."
        ),
    )
    delivery_date_end: str | None = Field(
        default=None,
        description=(
            "Data final no formato AAAA-MM-DD quando a entrega tiver um "
            "intervalo de datas, sincronizada com deadlines."
        ),
    )
    delivery_reference_raw: str | None = Field(
        default=None,
        description="Expressão original do prazo de entrega presente na mensagem.",
    )
    has_date_conflict: bool = Field(
        default=False,
        description=(
            "Indicador global: True quando houver conflito entre data explícita, "
            "dia da semana ou outra referência em qualquer prazo identificado na mensagem."
        ),
    )
    date_conflict_description: str | None = Field(
        default=None,
        description="Explicação clara de quais referências de prazo entram em conflito.",
    )
    response_deadline: str | None = Field(
        default=None,
        description=(
            "Data limite de resposta ou retorno solicitada na mensagem (AAAA-MM-DD), "
            "sincronizada com o prazo de 'resposta' em deadlines."
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
            "disponíveis (AAAA-MM-DD), sincronizada com deadlines."
        ),
    )
    document_availability_date_end: str | None = Field(
        default=None,
        description=(
            "Último dia do período de disponibilização de documentos (AAAA-MM-DD), "
            "sincronizada com deadlines."
        ),
    )
    document_availability_raw: str | None = Field(
        default=None,
        description="Expressão original do prazo de disponibilização de documentos.",
    )
    deadlines: list[TriageDeadline] = Field(
        default_factory=list,
        description=(
            "Fonte canônica dos prazos identificados na mensagem, distinguindo "
            "entrega, resposta e disponibilização de documentos."
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
            and self.document_availability_end_as_date
            < self.document_availability_start_as_date
        ):
            raise ValueError(
                "document_availability_date_end must be greater than or equal to "
                "document_availability_date_start."
            )

        grouped: dict[DeadlineAction, list[TriageDeadline]] = {}
        for item in self.deadlines:
            grouped.setdefault(item.action, []).append(item)

        canonical: dict[DeadlineAction, TriageDeadline] = {}

        input_has_date_conflict = self.has_date_conflict

        # Fonte de verdade: `deadlines` prevalece sobre os campos individuais quando
        # ambos possuem datas divergentes; campos individuais preenchem lacunas quando
        # a ação ou a data estiver ausente em `deadlines` (sem conflito).
        # Conflitos são preservados individualmente por ação, sem contaminar prazos válidos.
        if DeadlineAction.DELIVERY in grouped:
            dl = _consolidate_action_entries(
                DeadlineAction.DELIVERY,
                grouped[DeadlineAction.DELIVERY],
            )
            effective_start = (
                dl.date_start
                if dl.date_start is not None or dl.has_conflict
                else self.delivery_date_start
            )
            effective_end = (
                dl.date_end
                if dl.date_start is not None or dl.has_conflict
                else self.delivery_date_end
            )
            effective_raw = dl.reference_raw or self.delivery_reference_raw
            canonical[DeadlineAction.DELIVERY] = TriageDeadline(
                action=DeadlineAction.DELIVERY,
                date_start=effective_start,
                date_end=effective_end,
                reference_raw=effective_raw,
                has_conflict=dl.has_conflict,
                conflict_description=dl.conflict_description,
            )
        elif self.delivery_date_start is not None:
            canonical[DeadlineAction.DELIVERY] = TriageDeadline(
                action=DeadlineAction.DELIVERY,
                date_start=self.delivery_date_start,
                date_end=self.delivery_date_end,
                reference_raw=self.delivery_reference_raw,
            )

        if DeadlineAction.RESPONSE in grouped:
            dl = _consolidate_action_entries(
                DeadlineAction.RESPONSE,
                grouped[DeadlineAction.RESPONSE],
            )
            effective_start = (
                dl.date_start
                if dl.date_start is not None or dl.has_conflict
                else self.response_deadline
            )
            effective_raw = dl.reference_raw or self.response_deadline_raw
            canonical[DeadlineAction.RESPONSE] = TriageDeadline(
                action=DeadlineAction.RESPONSE,
                date_start=effective_start,
                date_end=dl.date_end,
                reference_raw=effective_raw,
                has_conflict=dl.has_conflict,
                conflict_description=dl.conflict_description,
            )
        elif self.response_deadline is not None:
            canonical[DeadlineAction.RESPONSE] = TriageDeadline(
                action=DeadlineAction.RESPONSE,
                date_start=self.response_deadline,
                reference_raw=self.response_deadline_raw,
            )

        if DeadlineAction.DOCUMENT_AVAILABILITY in grouped:
            dl = _consolidate_action_entries(
                DeadlineAction.DOCUMENT_AVAILABILITY,
                grouped[DeadlineAction.DOCUMENT_AVAILABILITY],
            )
            effective_start = (
                dl.date_start
                if dl.date_start is not None or dl.has_conflict
                else self.document_availability_date_start
            )
            effective_end = (
                dl.date_end
                if dl.date_start is not None or dl.has_conflict
                else self.document_availability_date_end
            )
            effective_raw = dl.reference_raw or self.document_availability_raw
            canonical[DeadlineAction.DOCUMENT_AVAILABILITY] = TriageDeadline(
                action=DeadlineAction.DOCUMENT_AVAILABILITY,
                date_start=effective_start,
                date_end=effective_end,
                reference_raw=effective_raw,
                has_conflict=dl.has_conflict,
                conflict_description=dl.conflict_description,
            )
        elif self.document_availability_date_start is not None:
            canonical[DeadlineAction.DOCUMENT_AVAILABILITY] = TriageDeadline(
                action=DeadlineAction.DOCUMENT_AVAILABILITY,
                date_start=self.document_availability_date_start,
                date_end=self.document_availability_date_end,
                reference_raw=self.document_availability_raw,
            )

        # Quando `has_date_conflict=True` foi informado globalmente, mas nenhuma ação
        # individual em `deadlines` já está marcada com `has_conflict=True`:
        # - se há uma ação sem data com texto bruto (`*_raw`), atribui o conflito a ela
        #   sem invalidar os demais prazos válidos;
        # - senão, se existe exatamente um prazo na mensagem, propaga o conflito a ele
        #   (compatibilidade com contratos legados de prazo único);
        # - senão, se não existe nenhum prazo, registra o conflito para sinalização;
        # - quando há múltiplos prazos válidos sem conflito individual indicado, preserva
        #   os indicadores individuais intactos e mantém o indicador global ativo.
        if input_has_date_conflict and not any(
            d.has_conflict for d in canonical.values()
        ):
            raw_by_action: dict[DeadlineAction, str | None] = {
                DeadlineAction.DELIVERY: self.delivery_reference_raw,
                DeadlineAction.RESPONSE: self.response_deadline_raw,
                DeadlineAction.DOCUMENT_AVAILABILITY: self.document_availability_raw,
            }
            missing_actions_with_raw = [
                action
                for action in _CANONICAL_ACTION_ORDER
                if action not in canonical and raw_by_action[action]
            ]
            if missing_actions_with_raw:
                for action in missing_actions_with_raw:
                    canonical[action] = TriageDeadline(
                        action=action,
                        date_start=None,
                        date_end=None,
                        reference_raw=raw_by_action[action],
                        has_conflict=True,
                        conflict_description=self.date_conflict_description,
                    )
            elif len(canonical) == 1:
                sole_action, sole_dl = next(iter(canonical.items()))
                canonical[sole_action] = sole_dl.model_copy(
                    update={
                        "has_conflict": True,
                        "conflict_description": (
                            sole_dl.conflict_description
                            or self.date_conflict_description
                        ),
                    }
                )
            elif len(canonical) == 0:
                canonical[DeadlineAction.DELIVERY] = TriageDeadline(
                    action=DeadlineAction.DELIVERY,
                    date_start=None,
                    date_end=None,
                    reference_raw=self.delivery_reference_raw,
                    has_conflict=True,
                    conflict_description=self.date_conflict_description,
                )

        conflicting_actions = [
            action for action, dl in canonical.items() if dl.has_conflict
        ]
        if (
            len(conflicting_actions) == 1
            and self.date_conflict_description
            and not canonical[conflicting_actions[0]].conflict_description
        ):
            sole_conflict_action = conflicting_actions[0]
            canonical[sole_conflict_action] = canonical[sole_conflict_action].model_copy(
                update={"conflict_description": self.date_conflict_description}
            )

        self.deadlines = [
            canonical[action]
            for action in _CANONICAL_ACTION_ORDER
            if action in canonical
        ]

        # Projeta a fonte de verdade canônica de volta para todos os campos individuais
        # garantindo consistência total mesmo em caso de divergência na entrada.
        delivery_dl = canonical.get(DeadlineAction.DELIVERY)
        if delivery_dl is not None:
            self.delivery_date_start = delivery_dl.date_start
            self.delivery_date_end = delivery_dl.date_end
            self.delivery_reference_raw = delivery_dl.reference_raw
        else:
            self.delivery_date_start = None
            self.delivery_date_end = None

        response_dl = canonical.get(DeadlineAction.RESPONSE)
        if response_dl is not None:
            self.response_deadline = response_dl.date_start
            self.response_deadline_raw = response_dl.reference_raw
        else:
            self.response_deadline = None

        doc_dl = canonical.get(DeadlineAction.DOCUMENT_AVAILABILITY)
        if doc_dl is not None:
            self.document_availability_date_start = doc_dl.date_start
            self.document_availability_date_end = doc_dl.date_end
            self.document_availability_raw = doc_dl.reference_raw
        else:
            self.document_availability_date_start = None
            self.document_availability_date_end = None

        self.has_date_conflict = input_has_date_conflict or any(
            d.has_conflict for d in self.deadlines
        )
        if self.has_date_conflict and not self.date_conflict_description:
            self.date_conflict_description = next(
                (d.conflict_description for d in self.deadlines if d.conflict_description),
                None,
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
