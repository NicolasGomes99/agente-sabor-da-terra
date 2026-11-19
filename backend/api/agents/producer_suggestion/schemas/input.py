from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from ...config import PERNAMBUCO_TIMEZONE, to_pernambuco_date
from ...consultation.schemas.input import ConsultationSourceItem


def _normalize_iso_date_str(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return to_pernambuco_date(value).isoformat()


def _normalize_id_str(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return cleaned


def _parse_optional_decimal(value: Decimal | float | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    dec = Decimal(str(value).strip())
    if not dec.is_finite():
        raise ValueError("Numeric quantity must be finite.")
    return dec


class BalanceStatus(StrEnum):
    AVAILABLE = "disponivel"
    FULLY_ALLOCATED = "integralmente_alocado"
    INDETERMINED = "indeterminado"


class ProductCatalogRef(BaseModel):
    product_id: str = Field(
        min_length=1,
        description="Identificador (UUID ou código) do produto no catálogo.",
    )
    product_name: str = Field(
        min_length=1,
        description="Nome padronizado do produto no catálogo.",
    )

    @field_validator("product_id", mode="before")
    @classmethod
    def _coerce_product_id(cls, value: UUID | str) -> str:
        normalized = _normalize_id_str(value)
        if not normalized:
            raise ValueError("product_id must not be blank.")
        return normalized

    @field_validator("product_name")
    @classmethod
    def _strip_product_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("product_name must not be blank.")
        return stripped


class OrderItemBalanceContract(BaseModel):
    """Contrato de item de pedido e saldo operacional retornado pela aplicação (#36 / #28)."""

    order_item_id: str = Field(
        min_length=1,
        description="Identificador do ItemPedido.",
    )
    product_id: str = Field(
        min_length=1,
        description="Identificador do Produto no catálogo.",
    )
    product_name: str = Field(
        min_length=1,
        description="Nome padronizado do produto solicitado.",
    )
    requested_quantity: Decimal | None = Field(
        default=None,
        description="Quantidade solicitada no item do pedido.",
    )
    allocated_quantity: Decimal | None = Field(
        default=Decimal(0),
        description="Soma das alocações operacionais vigentes do item na unidade do item.",
    )
    remaining_balance: Decimal | None = Field(
        default=None,
        description=(
            "Saldo a alocar informado pela aplicação (solicitado - alocações vigentes). "
            "None quando o saldo estiver indeterminado."
        ),
    )
    unit: str | None = Field(
        default=None,
        description="Unidade do item do pedido (ex.: kg, unidade, maço, dúzia).",
    )
    balance_status: BalanceStatus | None = Field(
        default=None,
        description="Situação operacional do saldo retornada pela aplicação.",
    )
    balance_pending_reason: str | None = Field(
        default=None,
        description="Motivo da pendência quando o saldo estiver indeterminado.",
    )
    item_conditions: str = Field(
        default="",
        description="Exigências específicas deste item (ex.: certificação orgânica).",
    )
    requires_organic_certification: bool | None = Field(
        default=None,
        description=(
            "Sinalização explícita de exigência de certificação orgânica para este item. "
            "Quando None, o avaliador infere a partir das condições do item, pedido e contrato."
        ),
    )

    @field_validator("order_item_id", "product_id", mode="before")
    @classmethod
    def _coerce_ids(cls, value: UUID | str) -> str:
        normalized = _normalize_id_str(value)
        if not normalized:
            raise ValueError("Identifier must not be blank.")
        return normalized

    @field_validator("product_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("product_name must not be blank.")
        return stripped

    @field_validator("requested_quantity", "allocated_quantity", "remaining_balance", mode="before")
    @classmethod
    def _coerce_decimals(
        cls,
        value: Decimal | float | str | None,
    ) -> Decimal | None:
        return _parse_optional_decimal(value)

    @model_validator(mode="after")
    def _validate_and_normalize_balance(self) -> "OrderItemBalanceContract":
        if self.requested_quantity is not None and self.requested_quantity <= Decimal(0):
            raise ValueError("requested_quantity must be greater than zero.")
        if self.allocated_quantity is not None and self.allocated_quantity < Decimal(0):
            raise ValueError("allocated_quantity must not be negative.")
        if self.remaining_balance is not None and self.remaining_balance < Decimal(0):
            raise ValueError("remaining_balance must not be negative.")

        if self.balance_status == BalanceStatus.INDETERMINED:
            self.remaining_balance = None
            if not self.balance_pending_reason:
                self.balance_pending_reason = (
                    "Saldo operacional indeterminado por pendência de quantidade "
                    "ou unidade nas alocações do item."
                )
            return self

        if self.remaining_balance is None:
            if (
                self.requested_quantity is not None
                and self.allocated_quantity is not None
                and self.unit
                and not self.balance_pending_reason
            ):
                computed = self.requested_quantity - self.allocated_quantity
                self.remaining_balance = max(computed, Decimal(0))
            else:
                self.balance_status = BalanceStatus.INDETERMINED
                if not self.balance_pending_reason:
                    self.balance_pending_reason = (
                        "Faltam dados de quantidade solicitada, unidade ou saldo "
                        "operacional retornado pela aplicação."
                    )
                return self

        if self.balance_status is None:
            self.balance_status = (
                BalanceStatus.FULLY_ALLOCATED
                if self.remaining_balance == Decimal(0)
                else BalanceStatus.AVAILABLE
            )
        elif (
            self.balance_status == BalanceStatus.FULLY_ALLOCATED
            and self.remaining_balance != Decimal(0)
        ):
            raise ValueError(
                "balance_status='integralmente_alocado' requires remaining_balance == 0."
            )
        elif (
            self.balance_status == BalanceStatus.AVAILABLE
            and self.remaining_balance == Decimal(0)
        ):
            self.balance_status = BalanceStatus.FULLY_ALLOCATED

        return self


class OrderToolContract(BaseModel):
    """Contrato de pedido retornado pela ferramenta da aplicação (alinhado a Order + #36 + #28)."""

    order_id: str = Field(
        min_length=1,
        description="Identificador do pedido cadastrado (UUID ou código).",
    )
    buyer: str = Field(
        min_length=1,
        description="Nome do comprador do pedido.",
    )
    conditions: str = Field(
        default="",
        description="Condições de atendimento e exigências registradas no pedido.",
    )
    contract_reference: str | None = Field(
        default=None,
        description="Referência a contrato citado no pedido (ex.: 'Contrato nº 045/2026-PNAE').",
    )
    delivery_start_date: str = Field(
        description="Data única ou data inicial do intervalo de entrega do pedido (AAAA-MM-DD).",
    )
    delivery_end_date: str | None = Field(
        default=None,
        description="Data final do intervalo de entrega quando houver intervalo (AAAA-MM-DD).",
    )
    exact_delivery_date: str | None = Field(
        default=None,
        description=(
            "Data exata de entrega quando já tiver sido informada pelo funcionário "
            "para o atendimento (AAAA-MM-DD)."
        ),
    )
    cancelled: bool = Field(
        default=False,
        description="True se o pedido estiver cancelado.",
    )
    order_version: int | None = Field(
        default=None,
        ge=1,
        description="Versão de controle otimista do pedido cadastrado (#36).",
    )
    products_legacy_text: str = Field(
        default="",
        description="Descrição legada de produtos quando o pedido ainda não possui itens estruturados.",
    )
    items: list[OrderItemBalanceContract] = Field(
        default_factory=list,
        description="Itens estruturados do pedido com seus saldos operacionais.",
    )

    @classmethod
    def from_order_response(
        cls,
        order_obj: Any,
        *,
        item_balances: dict[str, dict[str, Any]] | None = None,
        contract_reference: str | None = None,
        exact_delivery_date: date | datetime | str | None = None,
    ) -> "OrderToolContract":
        """Converte OrderResponse/Order (#36) para OrderToolContract, mesclando saldos da #28."""
        balances_by_id = {
            str(k).strip(): v for k, v in (item_balances or {}).items()
        }
        raw_items = getattr(order_obj, "items", None) or []
        converted_items: list[OrderItemBalanceContract] = []
        for raw_item in raw_items:
            item_id = str(getattr(raw_item, "id", getattr(raw_item, "order_item_id", "")))
            product_obj = getattr(raw_item, "product", None)
            product_id = str(
                getattr(raw_item, "product_id", None)
                or getattr(product_obj, "id", "")
            )
            product_name = str(
                getattr(product_obj, "name", None)
                or getattr(raw_item, "product_name", "")
            )
            balance_meta = balances_by_id.get(item_id, {})
            converted_items.append(
                OrderItemBalanceContract(
                    order_item_id=item_id,
                    product_id=product_id,
                    product_name=product_name,
                    requested_quantity=getattr(
                        raw_item, "quantity", getattr(raw_item, "requested_quantity", None)
                    ),
                    allocated_quantity=balance_meta.get("allocated_quantity", Decimal(0)),
                    remaining_balance=balance_meta.get("remaining_balance"),
                    unit=getattr(raw_item, "unit", None),
                    balance_status=balance_meta.get("balance_status"),
                    balance_pending_reason=balance_meta.get("balance_pending_reason"),
                    item_conditions=balance_meta.get("item_conditions", ""),
                    requires_organic_certification=balance_meta.get(
                        "requires_organic_certification"
                    ),
                )
            )
        return cls(
            order_id=str(getattr(order_obj, "id", getattr(order_obj, "order_id", ""))),
            buyer=str(order_obj.buyer),
            conditions=str(getattr(order_obj, "conditions", "") or ""),
            contract_reference=contract_reference,
            delivery_start_date=order_obj.delivery_start_date,
            delivery_end_date=getattr(order_obj, "delivery_end_date", None),
            exact_delivery_date=exact_delivery_date,
            cancelled=bool(getattr(order_obj, "cancelled", False)),
            order_version=getattr(order_obj, "version", None),
            products_legacy_text=str(
                getattr(order_obj, "products", None)
                or getattr(order_obj, "products_legacy_text", "")
                or ""
            ),
            items=converted_items,
        )

    @field_validator("order_id", mode="before")
    @classmethod
    def _coerce_order_id(cls, value: UUID | str) -> str:
        normalized = _normalize_id_str(value)
        if not normalized:
            raise ValueError("order_id must not be blank.")
        return normalized

    @field_validator("buyer")
    @classmethod
    def _strip_buyer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("buyer must not be blank.")
        return stripped

    @field_validator("delivery_start_date", mode="before")
    @classmethod
    def _normalize_start_date(cls, value: date | datetime | str) -> str:
        normalized = _normalize_iso_date_str(value)
        if normalized is None:
            raise ValueError("delivery_start_date is required.")
        return normalized

    @field_validator("delivery_end_date", "exact_delivery_date", mode="before")
    @classmethod
    def _normalize_optional_dates(
        cls,
        value: date | datetime | str | None,
    ) -> str | None:
        return _normalize_iso_date_str(value)

    @model_validator(mode="after")
    def _validate_delivery_window(self) -> "OrderToolContract":
        start = date.fromisoformat(self.delivery_start_date)
        end = (
            date.fromisoformat(self.delivery_end_date)
            if self.delivery_end_date is not None
            else start
        )
        if end < start:
            raise ValueError(
                "delivery_end_date must be greater than or equal to delivery_start_date."
            )
        if self.exact_delivery_date is not None:
            exact = date.fromisoformat(self.exact_delivery_date)
            if exact < start or exact > end:
                raise ValueError(
                    "exact_delivery_date must fall within the order delivery window."
                )
        return self

    @property
    def needs_item_structuring(self) -> bool:
        return len(self.items) == 0

    @property
    def effective_window(self) -> tuple[date, date]:
        if self.exact_delivery_date is not None:
            exact = date.fromisoformat(self.exact_delivery_date)
            return exact, exact
        start = date.fromisoformat(self.delivery_start_date)
        end = (
            date.fromisoformat(self.delivery_end_date)
            if self.delivery_end_date is not None
            else start
        )
        return start, end


class ProducerCatalogItemContract(BaseModel):
    """Contrato de produtor retornado pela aplicação (alinhado a ProducerResponse da #23)."""

    producer_id: str = Field(
        min_length=1,
        description="Identificador único (UUID ou código) do produtor.",
    )
    code: str = Field(
        min_length=1,
        description="Código operacional do produtor (ex.: P001).",
    )
    name: str = Field(
        min_length=1,
        description="Nome completo do produtor.",
    )
    active: bool = Field(
        description="Situação cadastral do produtor (True=ativo, False=inativo).",
    )
    municipality: str | None = Field(
        default=None,
        description="Município do produtor.",
    )
    products: list[ProductCatalogRef] = Field(
        default_factory=list,
        description="Produtos associados ao produtor em ProducerProduct.",
    )

    @field_validator("producer_id", mode="before")
    @classmethod
    def _coerce_producer_id(cls, value: UUID | str) -> str:
        normalized = _normalize_id_str(value)
        if not normalized:
            raise ValueError("producer_id must not be blank.")
        return normalized

    @field_validator("code", "name")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank.")
        return stripped

    @classmethod
    def from_producer_response(cls, producer_obj: Any) -> "ProducerCatalogItemContract":
        """Converte ProducerResponse (#23) ou objeto compatível para o contrato das tools."""
        raw_products = getattr(producer_obj, "products", None) or []
        products = [
            ProductCatalogRef(
                product_id=str(getattr(prod, "id", getattr(prod, "product_id", ""))),
                product_name=str(getattr(prod, "name", getattr(prod, "product_name", ""))),
            )
            for prod in raw_products
        ]
        return cls(
            producer_id=str(getattr(producer_obj, "id", getattr(producer_obj, "producer_id", ""))),
            code=str(producer_obj.code),
            name=str(producer_obj.name),
            active=bool(producer_obj.active),
            municipality=getattr(producer_obj, "municipality", None),
            products=products,
        )


class UnitEquivalence(BaseModel):
    """Equivalência conhecida de unidades para comparação demanda vs capacidade."""

    from_unit: str = Field(min_length=1, description="Unidade de origem (ex.: caixa).")
    to_unit: str = Field(min_length=1, description="Unidade de destino (ex.: kg).")
    factor: Decimal = Field(
        description="Fator multiplicativo positivo: 1 from_unit = factor * to_unit.",
    )
    product_name: str | None = Field(
        default=None,
        description="Produto específico ao qual a equivalência se aplica, quando não for geral.",
    )
    source_id: str | None = Field(
        default=None,
        description="Identificador da fonte documental que estabelece essa equivalência.",
    )

    @field_validator("from_unit", "to_unit")
    @classmethod
    def _strip_units(cls, value: str) -> str:
        stripped = value.strip().lower()
        if not stripped:
            raise ValueError("Unit must not be blank.")
        return stripped

    @field_validator("factor", mode="before")
    @classmethod
    def _coerce_factor(cls, value: Decimal | float | str) -> Decimal:
        parsed = _parse_optional_decimal(value)
        if parsed is None or parsed <= Decimal(0):
            raise ValueError("factor must be greater than zero.")
        return parsed


class ProducerSuggestionInput(BaseModel):
    """Entrada do fluxo de sugestão de produtores para um pedido cadastrado (#25)."""

    order_id: str = Field(
        min_length=1,
        description="Identificador do pedido cadastrado a analisar.",
    )
    reference_date: datetime | date | str | None = Field(
        default=None,
        description=(
            "Data de referência da consulta (fuso de Pernambuco). "
            "Quando omitida, utiliza a data atual."
        ),
    )
    exact_delivery_date: datetime | date | str | None = Field(
        default=None,
        description=(
            "Data exata de entrega informada pelo funcionário na conversa, "
            "sobrescrevendo o intervalo do pedido quando presente."
        ),
    )
    question: str | None = Field(
        default=None,
        description="Pergunta ou instrução adicional do funcionário sobre a sugestão.",
    )
    unit_equivalences: list[UnitEquivalence] = Field(
        default_factory=list,
        description="Equivalências conhecidas de unidades autorizadas para conversão.",
    )
    sources: list[ConsultationSourceItem] = Field(
        default_factory=list,
        description=(
            "Fontes documentais e registros recuperados (certificações, contratos, "
            "sazonalidade, fichas técnicas e lotes históricos)."
        ),
    )

    @field_validator("order_id", mode="before")
    @classmethod
    def _coerce_order_id(cls, value: UUID | str) -> str:
        normalized = _normalize_id_str(value)
        if not normalized:
            raise ValueError("order_id must not be blank.")
        return normalized

    @field_validator("reference_date", "exact_delivery_date")
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

    @property
    def resolved_exact_delivery_date(self) -> date | None:
        if self.exact_delivery_date is None:
            return None
        return to_pernambuco_date(self.exact_delivery_date)
