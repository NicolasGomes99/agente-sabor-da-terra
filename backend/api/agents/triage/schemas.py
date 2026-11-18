from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import to_pernambuco_date


class RequestType(StrEnum):
    ORDER = "pedido"
    CONSULTATION = "consulta"
    OFFER = "oferta"
    NOTICE = "comunicado"
    UNIDENTIFIED = "nao_identificado"


class UrgencyLevel(StrEnum):
    URGENT = "urgente"
    NORMAL = "normal"
    UNDETERMINED = "indeterminada"


class PendingCategory(StrEnum):
    DATE_CONFLICT = "conflito_de_data"
    MISSING_DEADLINE = "prazo_ausente_ou_incerto"
    AMBIGUOUS_QUANTITY = "quantidade_agregada_ou_ambigua"
    UNDEFINED_PRODUCT = "produto_indefinido"
    MISSING_UNIT = "unidade_ausente_ou_ambigua"
    CONTRACT_OR_REQUIREMENT_CHECK = "verificacao_de_exigencia_ou_contrato"
    SENSITIVE_OR_DOCUMENT_REQUEST = "solicitacao_de_documento_ou_dado_sensivel"
    OTHER = "outro"


def _normalize_iso_date_str(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    parsed = to_pernambuco_date(value)
    return parsed.isoformat()


def classify_urgency(
    received_date: date,
    delivery_date_start: date | None,
    declared_urgency: bool,
    has_date_conflict: bool = False,
) -> tuple[UrgencyLevel, str]:
    """Classifica urgência e gera motivo padrão segundo as regras de negócio do RF04."""
    if declared_urgency:
        if (
            delivery_date_start is not None
            and not has_date_conflict
            and delivery_date_start <= received_date + timedelta(days=1)
        ):
            return (
                UrgencyLevel.URGENT,
                (
                    f"Urgência declarada na mensagem e entrega prevista para "
                    f"{delivery_date_start.isoformat()} (até o dia seguinte ao "
                    f"recebimento em {received_date.isoformat()})."
                ),
            )
        return (
            UrgencyLevel.URGENT,
            "Urgência declarada explicitamente pelo remetente na mensagem.",
        )

    if has_date_conflict or delivery_date_start is None:
        if has_date_conflict:
            return (
                UrgencyLevel.UNDETERMINED,
                (
                    "Prazo com referências de data em conflito e sem urgência "
                    "declarada na mensagem."
                ),
            )
        return (
            UrgencyLevel.UNDETERMINED,
            (
                "Faltam dados de data de entrega para classificar o prazo e não "
                "há urgência declarada."
            ),
        )

    if delivery_date_start <= received_date + timedelta(days=1):
        return (
            UrgencyLevel.URGENT,
            (
                f"Entrega prevista para {delivery_date_start.isoformat()}, no dia "
                f"do recebimento ({received_date.isoformat()}) ou no dia seguinte."
            ),
        )

    return (
        UrgencyLevel.NORMAL,
        (
            f"Entrega prevista para {delivery_date_start.isoformat()}, após o dia "
            f"seguinte ao recebimento ({received_date.isoformat()}), sem urgência "
            f"declarada."
        ),
    )


class TriageInput(BaseModel):
    message_text: str = Field(
        min_length=1,
        description="Texto original da mensagem recebida na triagem.",
    )
    received_at: datetime | date | str = Field(
        description="Data ou data/hora de recebimento da mensagem.",
    )
    sender: str | None = Field(
        default=None,
        description="Identificação do remetente no canal de origem.",
    )
    buyer_name: str | None = Field(
        default=None,
        description="Nome do comprador ou contato associado, quando conhecido.",
    )
    channel: str | None = Field(
        default=None,
        description="Canal de entrada (ex.: email, whatsapp, formulario_web).",
    )
    source_id: str | None = Field(
        default=None,
        description="Identificador externo da mensagem, quando disponível.",
    )

    @field_validator("message_text")
    @classmethod
    def _validate_message_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message_text must not be blank.")
        return stripped

    @field_validator("received_at")
    @classmethod
    def _validate_received_at(
        cls,
        value: datetime | date | str,
    ) -> datetime | date | str:
        to_pernambuco_date(value)
        return value

    @property
    def received_date(self) -> date:
        return to_pernambuco_date(self.received_at)


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
        gt=0,
        description=(
            "Quantidade numérica individual do item, quando definida sem "
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


class TriagePendingItem(BaseModel):
    category: PendingCategory = Field(
        description="Categoria da pendência ou ponto que exige atenção/esclarecimento.",
    )
    description: str = Field(
        min_length=1,
        description="Descrição objetiva da pendência em português.",
    )
    question_for_staff: str = Field(
        min_length=1,
        description=(
            "Pergunta específica de esclarecimento ou orientação de verificação "
            "para o funcionário."
        ),
    )


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
        description="Motivo da classificação de urgência em português.",
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

    @property
    def received_date(self) -> date:
        return date.fromisoformat(self.received_date_reference)

    @model_validator(mode="after")
    def _enforce_business_rules(self) -> "TriageAnalysis":
        expected_urgency, default_reason = classify_urgency(
            received_date=self.received_date,
            delivery_date_start=self.extracted_data.delivery_start_as_date,
            declared_urgency=self.declared_urgency,
            has_date_conflict=self.extracted_data.has_date_conflict,
        )
        if self.urgency != expected_urgency:
            self.urgency = expected_urgency
            self.urgency_reason = default_reason
        elif not self.urgency_reason.strip():
            self.urgency_reason = default_reason

        existing_categories = {item.category for item in self.pending_items}

        if (
            self.extracted_data.has_date_conflict
            and PendingCategory.DATE_CONFLICT not in existing_categories
        ):
            conflict_desc = (
                self.extracted_data.date_conflict_description
                or "Conflito entre as referências de prazo informadas na mensagem."
            )
            self.pending_items.append(
                TriagePendingItem(
                    category=PendingCategory.DATE_CONFLICT,
                    description=conflict_desc,
                    question_for_staff=(
                        f"Há conflito no prazo informado ({conflict_desc}). "
                        f"Qual data de entrega deve ser considerada?"
                    ),
                )
            )
            existing_categories.add(PendingCategory.DATE_CONFLICT)

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
