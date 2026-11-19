from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


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


def classify_urgency(
    received_date: date,
    delivery_date_start: date | None,
    declared_urgency: bool,
    has_date_conflict: bool = False,
) -> tuple[UrgencyLevel, str]:
    """Classifica urgência e gera motivo padrão segundo as regras de negócio do RF04."""
    next_day = received_date + timedelta(days=1)

    if declared_urgency:
        if (
            delivery_date_start is not None
            and not has_date_conflict
            and received_date <= delivery_date_start <= next_day
        ):
            return (
                UrgencyLevel.URGENT,
                (
                    f"Urgência declarada na mensagem e entrega prevista para "
                    f"{delivery_date_start.isoformat()} (até o dia seguinte ao "
                    f"recebimento em {received_date.isoformat()})."
                ),
            )
        if (
            delivery_date_start is not None
            and not has_date_conflict
            and delivery_date_start < received_date
        ):
            return (
                UrgencyLevel.URGENT,
                (
                    f"Urgência declarada explicitamente pelo remetente na mensagem "
                    f"(prazo informado {delivery_date_start.isoformat()} é anterior "
                    f"ao recebimento em {received_date.isoformat()})."
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

    if delivery_date_start < received_date:
        return (
            UrgencyLevel.UNDETERMINED,
            (
                f"Inconsistência no prazo: a data de entrega informada "
                f"({delivery_date_start.isoformat()}) é anterior à data de "
                f"recebimento ({received_date.isoformat()}) e não há urgência "
                f"declarada."
            ),
        )

    if delivery_date_start <= next_day:
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
