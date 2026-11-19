from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from ...consultation.schemas.response import CitedSource
from .input import BalanceStatus


class CandidateProofStatus(StrEnum):
    SUFFICIENT_PROOF = "comprovacao_suficiente"
    NEEDS_CONFIRMATION = "depende_confirmacao"


class CertificationCoverageStatus(StrEnum):
    NOT_REQUIRED = "nao_exigida"
    VALID_FULL = "vigente_integral"
    VALID_PARTIAL = "vigente_parcial"
    EXPIRED = "vencida"
    PRODUCT_NOT_COVERED = "produto_nao_coberto"
    UNVERIFIED = "nao_comprovada"


class CapacityComparisonStatus(StrEnum):
    COMPATIBLE = "compativel"
    ABOVE_ESTIMATED_CAPACITY = "acima_capacidade_estimada"
    INCOMPATIBLE_UNIT_OR_PERIOD = "unidade_ou_periodo_incompativel"
    NOT_INFORMED = "nao_informada"


class ExcludedProducerInfo(BaseModel):
    """Produtor descartado da sugestão por incompatibilidade comprovada (RF14)."""

    producer_id: str = Field(min_length=1, description="Identificador do produtor.")
    producer_code: str = Field(min_length=1, description="Código do produtor (ex.: P015).")
    producer_name: str = Field(min_length=1, description="Nome do produtor.")
    reasons: list[str] = Field(
        default_factory=list,
        description="Motivos objetivos pelos quais o produtor foi excluído da sugestão.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores das fontes que comprovam a exclusão.",
    )


class ProducerCandidateSuggestion(BaseModel):
    """Candidato sugerido para atender a um item do pedido, com evidências e pendências."""

    producer_id: str = Field(min_length=1, description="Identificador do produtor.")
    producer_code: str = Field(min_length=1, description="Código do produtor (ex.: P002).")
    producer_name: str = Field(min_length=1, description="Nome completo do produtor.")
    proof_status: CandidateProofStatus = Field(
        description=(
            "'comprovacao_suficiente' quando atende integralmente às exigências "
            "documentais verificáveis; 'depende_confirmacao' quando alguma exigência "
            "ou vigência documental ainda carece de comprovação."
        ),
    )
    certification_status: CertificationCoverageStatus = Field(
        default=CertificationCoverageStatus.NOT_REQUIRED,
        description="Resultado da verificação de certificação orgânica para o item e prazo.",
    )
    certification_covered_start: str | None = Field(
        default=None,
        description=(
            "Data inicial coberta pela certificação quando houver cobertura parcial "
            "ou integral do intervalo (AAAA-MM-DD)."
        ),
    )
    certification_covered_end: str | None = Field(
        default=None,
        description=(
            "Data final coberta pela certificação dentro do prazo avaliado (AAAA-MM-DD)."
        ),
    )
    catalog_association_note: str = Field(
        default=(
            "Associação cadastral produtor-produto identifica possível fornecedor, "
            "mas não comprova disponibilidade operacional confirmada."
        ),
        description="Nota distinguindo vínculo de catálogo de disponibilidade confirmada.",
    )
    seasonality_summary: str | None = Field(
        default=None,
        description="Resumo da sazonalidade do produto no período previsto de entrega.",
    )
    estimated_capacity_summary: str | None = Field(
        default=None,
        description="Resumo da capacidade estimada documentada do produtor e comparação com o saldo.",
    )
    capacity_comparison_status: CapacityComparisonStatus = Field(
        default=CapacityComparisonStatus.NOT_INFORMED,
        description="Resultado da comparação entre saldo a alocar e capacidade estimada.",
    )
    historical_supply_summary: str | None = Field(
        default=None,
        description="Resumo de registros históricos de fornecimento (lotes.csv) na base.",
    )
    availability_confirmed: bool = Field(
        default=False,
        description=(
            "Sempre False nas sugestões do assistente: disponibilidade para quantidade "
            "e data propostas depende de confirmação operacional do funcionário."
        ),
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Motivos objetivos que fundamentam a sugestão deste produtor.",
    )
    pending_confirmations: list[str] = Field(
        default_factory=list,
        description=(
            "Itens que o funcionário ainda precisa confirmar (ex.: disponibilidade "
            "para quantidade e data propostas, vigência de DAP/CAF, data dentro da "
            "cobertura parcial do certificado)."
        ),
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores das fontes que sustentam esta sugestão.",
    )


class AlternativeProductSuggestion(BaseModel):
    """Sugestão opcional de produto alternativo quando não há candidato apto (RF14)."""

    replaces_order_item_id: str = Field(
        min_length=1,
        description="Identificador do item do pedido que este produto alternativo substituiria.",
    )
    replaces_product_name: str = Field(
        min_length=1,
        description="Nome do produto original do item que seria substituído.",
    )
    alternative_product_name: str = Field(
        min_length=1,
        description="Nome do produto alternativo sugerido.",
    )
    reason: str = Field(
        min_length=1,
        description="Justificativa técnica/operacional para sugerir a alternativa.",
    )
    candidate_producers_summary: str = Field(
        min_length=1,
        description="Produtores ativos associados ao produto alternativo, se disponíveis.",
    )
    requires_staff_approval: bool = Field(
        default=True,
        description="Sempre True: cabe ao funcionário decidir se aceita a alternativa.",
    )
    pending_confirmations: list[str] = Field(
        default_factory=list,
        description="Confirmações necessárias caso o funcionário aceite a alternativa.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Identificadores das fontes que sustentam a sugestão alternativa.",
    )


class OrderItemSuggestionResult(BaseModel):
    """Resultado da análise e sugestão de produtores para um item específico do pedido."""

    order_item_id: str = Field(min_length=1, description="Identificador do item do pedido.")
    product_id: str = Field(min_length=1, description="Identificador do produto do item.")
    product_name: str = Field(min_length=1, description="Nome padronizado do produto.")
    requested_quantity: float | None = Field(
        default=None,
        description="Quantidade originalmente solicitada no item.",
    )
    allocated_quantity: float | None = Field(
        default=None,
        description="Total de alocações operacionais vigentes do item.",
    )
    remaining_balance: float | None = Field(
        default=None,
        description="Saldo a alocar informado pela aplicação (None se indeterminado).",
    )
    unit: str | None = Field(
        default=None,
        description="Unidade do item do pedido.",
    )
    balance_status: BalanceStatus = Field(
        description="Situação do saldo do item ('disponivel', 'integralmente_alocado' ou 'indeterminado').",
    )
    allocation_message: str = Field(
        min_length=1,
        description="Resumo objetivo da situação do saldo e da quantidade considerada na sugestão.",
    )
    organic_certification_required: bool = Field(
        default=False,
        description="True quando o pedido ou o contrato citado exige certificação orgânica para o item.",
    )
    candidates: list[ProducerCandidateSuggestion] = Field(
        default_factory=list,
        description="Produtores candidatos elegíveis, com indicação de comprovação suficiente ou pendente.",
    )
    excluded_producers: list[ExcludedProducerInfo] = Field(
        default_factory=list,
        description="Produtores excluídos por incompatibilidade comprovada, com motivo.",
    )
    alternative_suggestions: list[AlternativeProductSuggestion] = Field(
        default_factory=list,
        description="Alternativas de produtos sugeridas (sempre identificando qual item substituiriam).",
    )
    insufficient_data: bool = Field(
        default=False,
        description="True quando não há candidato apto ou faltam dados suficientes para sugerir.",
    )
    insufficient_data_reason: str | None = Field(
        default=None,
        description="Motivo explicado ao funcionário quando não há candidato apto ou faltam dados.",
    )
    staff_decision_note: str | None = Field(
        default=None,
        description="Orientação deixando explícita a decisão do funcionário.",
    )

    @field_validator("requested_quantity")
    @classmethod
    def _validate_positive_requested(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("requested_quantity must be greater than zero.")
        return value

    @field_validator("allocated_quantity", "remaining_balance")
    @classmethod
    def _validate_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Quantity must not be negative.")
        return value


class ProducerSuggestionResponse(BaseModel):
    """Resposta estruturada do fluxo de sugestão de produtores para um pedido cadastrado (#25)."""

    order_id: str = Field(min_length=1, description="Identificador do pedido analisado.")
    buyer: str = Field(min_length=1, description="Comprador do pedido.")
    reference_date_used: str = Field(
        min_length=1,
        description="Data de referência considerada na análise (AAAA-MM-DD).",
    )
    evaluated_delivery_start: str = Field(
        min_length=1,
        description="Data inicial do prazo considerado na avaliação (AAAA-MM-DD).",
    )
    evaluated_delivery_end: str = Field(
        min_length=1,
        description="Data final do prazo considerado na avaliação (AAAA-MM-DD).",
    )
    exact_delivery_date_used: bool = Field(
        default=False,
        description="True quando a análise utilizou uma data exata de entrega já informada.",
    )
    summary: str = Field(
        min_length=1,
        description=(
            "Resposta textual completa em português apresentando os candidatos, "
            "motivos, exclusões, distinção de evidências, fontes e pendências a confirmar."
        ),
    )
    item_suggestions: list[OrderItemSuggestionResult] = Field(
        default_factory=list,
        description="Sugestões organizadas por item do pedido.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="União ordenada e sem duplicatas dos source_id citados na resposta.",
    )
    cited_sources: list[CitedSource] = Field(
        default_factory=list,
        description="Metadados das fontes citadas na resposta.",
    )
    general_pending_confirmations: list[str] = Field(
        default_factory=list,
        description="Pendências gerais do pedido ou do contrato que o funcionário precisa conferir.",
    )

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary must not be blank.")
        return stripped

    @model_validator(mode="after")
    def _sync_source_ids(self) -> "ProducerSuggestionResponse":
        ordered: list[str] = []
        seen: set[str] = set()

        def _add(sid: str) -> None:
            cleaned = sid.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered.append(cleaned)

        for sid in self.source_ids:
            _add(sid)
        for cited in self.cited_sources:
            _add(cited.source_id)
        for item in self.item_suggestions:
            for cand in item.candidates:
                for sid in cand.source_ids:
                    _add(sid)
            for excl in item.excluded_producers:
                for sid in excl.source_ids:
                    _add(sid)
            for alt in item.alternative_suggestions:
                for sid in alt.source_ids:
                    _add(sid)

        self.source_ids = ordered
        return self
