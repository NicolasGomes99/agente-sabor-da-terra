from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .classification import (
    PendingCategory,
    RequestType,
    TriagePendingItem,
    UrgencyLevel,
    evaluate_urgency,
)
from .extracted_data import TriageExtractedData
from .input import _normalize_iso_date_str
from .items import DeadlineAction

_ACTION_LABELS: dict[DeadlineAction, str] = {
    DeadlineAction.DELIVERY: "entrega",
    DeadlineAction.RESPONSE: "resposta",
    DeadlineAction.DOCUMENT_AVAILABILITY: "disponibilização de documentos",
}


class TriageAnalysis(BaseModel):
    summary: str = Field(
        min_length=1,
        description="Resumo em português da solicitação para exibição no cartão de triagem.",
    )
    request_type: RequestType = Field(
        description="Classificação da intenção principal da mensagem conforme RF04.",
    )
    additional_intents: list[str] = Field(
        default_factory=list,
        description="Intenções secundárias identificadas na mensagem, em português.",
    )
    declared_urgency: bool = Field(
        default=False,
        description="True quando o remetente declarou urgência explicitamente no texto.",
    )
    urgency: UrgencyLevel = Field(
        description="Classificação de urgência conforme RF04.",
    )
    urgency_reason: str = Field(
        min_length=1,
        description=(
            "Motivo da classificação de urgência em português, indicando a ação "
            "e a data consideradas quando a classificação se basear em prazo."
        ),
    )
    urgency_basis_action: DeadlineAction | None = Field(
        default=None,
        description=(
            "Ação solicitada ('entrega', 'resposta' ou 'disponibilizacao_de_documentos') "
            "que fundamentou a classificação de urgência, quando baseada em prazo."
        ),
    )
    urgency_basis_date: str | None = Field(
        default=None,
        description=(
            "Data considerada (AAAA-MM-DD) para a ação que fundamentou a classificação "
            "de urgência, quando baseada em prazo."
        ),
    )
    received_date_reference: str = Field(
        description="Data de recebimento considerada (AAAA-MM-DD, fuso de Pernambuco).",
    )
    extracted_data: TriageExtractedData = Field(
        default_factory=TriageExtractedData,
        description="Dados estruturados extraídos da mensagem.",
    )
    pending_items: list[TriagePendingItem] = Field(
        default_factory=list,
        description="Pendências, ambiguidades, conflitos e alertas identificados.",
    )
    requires_clarification: bool = Field(
        default=False,
        description="True quando há ambiguidades, conflitos ou dados faltantes a esclarecer.",
    )

    @field_validator("received_date_reference", mode="before")
    @classmethod
    def _validate_received_date_reference(
        cls,
        value: date | datetime | str,
    ) -> str:
        normalized = _normalize_iso_date_str(value)
        if normalized is None:
            raise ValueError("received_date_reference is required.")
        return normalized

    @field_validator("urgency_basis_date", mode="before")
    @classmethod
    def _validate_urgency_basis_date(
        cls,
        value: date | datetime | str | None,
    ) -> str | None:
        return _normalize_iso_date_str(value)

    @property
    def received_date(self) -> date:
        return date.fromisoformat(self.received_date_reference)

    @model_validator(mode="after")
    def _enforce_business_rules(self) -> "TriageAnalysis":
        decision = evaluate_urgency(
            received_date=self.received_date,
            declared_urgency=self.declared_urgency,
            deadlines=self.extracted_data.deadlines,
        )
        self.urgency = decision.level
        self.urgency_reason = decision.reason
        self.urgency_basis_action = decision.basis_action
        self.urgency_basis_date = (
            decision.basis_date.isoformat() if decision.basis_date is not None else None
        )

        existing_categories = {item.category for item in self.pending_items}

        if (
            (self.extracted_data.has_date_conflict or decision.conflicting_deadlines)
            and PendingCategory.DATE_CONFLICT not in existing_categories
        ):
            conflict_desc = (
                self.extracted_data.date_conflict_description
                or next(
                    (
                        d.conflict_description
                        for d in decision.conflicting_deadlines
                        if d.conflict_description
                    ),
                    None,
                )
                or "Conflito entre as referências de prazo informadas na mensagem."
            )
            self.pending_items.append(
                TriagePendingItem(
                    category=PendingCategory.DATE_CONFLICT,
                    description=conflict_desc,
                    question_for_staff=(
                        f"Há conflito no prazo informado ({conflict_desc}). "
                        f"Qual data deve ser considerada?"
                    ),
                )
            )
            existing_categories.add(PendingCategory.DATE_CONFLICT)

        for past_deadline in decision.past_deadlines:
            if past_deadline.start_as_date is None:
                continue
            iso_past = past_deadline.start_as_date.isoformat()
            already_flagged = any(
                iso_past in p.description or iso_past in p.question_for_staff
                for p in self.pending_items
            )
            if not already_flagged:
                action_label = _ACTION_LABELS[past_deadline.action]
                self.pending_items.append(
                    TriagePendingItem(
                        category=PendingCategory.DATE_CONFLICT,
                        description=(
                            f"Inconsistência de prazo: a data de {action_label} "
                            f"({iso_past}) é anterior à data de recebimento "
                            f"({self.received_date_reference}) e foi desconsiderada "
                            "na classificação."
                        ),
                        question_for_staff=(
                            f"O prazo de {action_label} informado ({iso_past}) é anterior "
                            f"ao recebimento ({self.received_date_reference}). "
                            "Qual data válida deve ser considerada?"
                        ),
                    )
                )

        for item in self.extracted_data.items:
            if item.ambiguous_or_aggregate:
                has_item_pending = any(
                    item.product.lower() in p.description.lower()
                    or item.product.lower() in p.question_for_staff.lower()
                    for p in self.pending_items
                    if p.category
                    in {
                        PendingCategory.AMBIGUOUS_QUANTITY,
                        PendingCategory.UNDEFINED_PRODUCT,
                        PendingCategory.MISSING_UNIT,
                    }
                )
                if not has_item_pending:
                    clarification = (
                        item.clarification_needed
                        or f"Confirmar quantidade, unidade ou especificação exata para '{item.product}'."
                    )
                    self.pending_items.append(
                        TriagePendingItem(
                            category=PendingCategory.AMBIGUOUS_QUANTITY,
                            description=(
                                f"Item '{item.product}' com quantidade agregada, "
                                f"ambígua ou especificação incompleta."
                            ),
                            question_for_staff=clarification,
                        )
                    )

        if (
            self.extracted_data.requested_documents_or_sensitive_data
            and PendingCategory.SENSITIVE_OR_DOCUMENT_REQUEST not in existing_categories
        ):
            requested_list = ", ".join(
                self.extracted_data.requested_documents_or_sensitive_data
            )
            self.pending_items.append(
                TriagePendingItem(
                    category=PendingCategory.SENSITIVE_OR_DOCUMENT_REQUEST,
                    description=(
                        f"O remetente solicitou documentos ou dados cadastrais/bancários: "
                        f"{requested_list}."
                    ),
                    question_for_staff=(
                        f"O remetente solicitou ({requested_list}). Quais documentos "
                        f"ou dados você autoriza compartilhar na resposta?"
                    ),
                )
            )

        if self.pending_items:
            self.requires_clarification = True

        return self
