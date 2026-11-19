from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from .items import DeadlineAction, TriageDeadline

_ACTION_LABELS: dict[DeadlineAction, str] = {
    DeadlineAction.DELIVERY: "entrega",
    DeadlineAction.RESPONSE: "resposta",
    DeadlineAction.DOCUMENT_AVAILABILITY: "disponibilização de documentos",
}


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


@dataclass(frozen=True)
class UrgencyDecision:
    level: UrgencyLevel
    reason: str
    basis_action: DeadlineAction | None
    basis_date: date | None
    past_deadlines: tuple[TriageDeadline, ...]
    conflicting_deadlines: tuple[TriageDeadline, ...]


def _fmt_date(value: date) -> str:
    return f"{value.strftime('%d/%m/%Y')} ({value.isoformat()})"


def _collect_deadlines(
    delivery_date_start: date | None,
    has_date_conflict: bool,
    response_deadline: date | None,
    document_availability_date_start: date | None,
    deadlines: Sequence[TriageDeadline] | None,
) -> list[TriageDeadline]:
    collected: list[TriageDeadline] = list(deadlines or [])
    present_actions = {d.action for d in collected}

    if (
        (delivery_date_start is not None or has_date_conflict)
        and DeadlineAction.DELIVERY not in present_actions
    ):
        collected.append(
            TriageDeadline(
                action=DeadlineAction.DELIVERY,
                date_start=delivery_date_start.isoformat() if delivery_date_start else None,
                has_conflict=has_date_conflict,
            )
        )
    if response_deadline is not None and DeadlineAction.RESPONSE not in present_actions:
        collected.append(
            TriageDeadline(
                action=DeadlineAction.RESPONSE,
                date_start=response_deadline.isoformat(),
            )
        )
    if (
        document_availability_date_start is not None
        and DeadlineAction.DOCUMENT_AVAILABILITY not in present_actions
    ):
        collected.append(
            TriageDeadline(
                action=DeadlineAction.DOCUMENT_AVAILABILITY,
                date_start=document_availability_date_start.isoformat(),
            )
        )
    return collected


def evaluate_urgency(
    received_date: date,
    delivery_date_start: date | None = None,
    declared_urgency: bool = False,
    has_date_conflict: bool = False,
    *,
    response_deadline: date | None = None,
    document_availability_date_start: date | None = None,
    deadlines: Sequence[TriageDeadline] | None = None,
) -> UrgencyDecision:
    """Avalia urgência considerando os três tipos de prazo (RF04) e retorna decisão estruturada."""
    next_day = received_date + timedelta(days=1)
    candidates = _collect_deadlines(
        delivery_date_start=delivery_date_start,
        has_date_conflict=has_date_conflict,
        response_deadline=response_deadline,
        document_availability_date_start=document_availability_date_start,
        deadlines=deadlines,
    )

    valid: list[tuple[date, TriageDeadline]] = []
    past: list[TriageDeadline] = []
    conflicting: list[TriageDeadline] = []

    for item in candidates:
        if item.has_conflict:
            conflicting.append(item)
            continue
        start = item.start_as_date
        if start is None:
            continue
        if start < received_date:
            past.append(item)
            continue
        valid.append((start, item))

    valid.sort(key=lambda pair: pair[0])
    past_tuple = tuple(past)
    conflict_tuple = tuple(conflicting)

    if valid:
        earliest_date, earliest_item = valid[0]
        action_label = _ACTION_LABELS[earliest_item.action]
        if earliest_date <= next_day:
            if earliest_date == received_date:
                timing_text = f"para o dia do recebimento ({_fmt_date(received_date)})"
            else:
                timing_text = f"para o dia seguinte ao recebimento ({_fmt_date(received_date)})"

            if declared_urgency:
                reason = (
                    f"Urgência declarada pelo remetente e prazo de {action_label} "
                    f"em {_fmt_date(earliest_date)}, {timing_text}."
                )
            elif earliest_item.action == DeadlineAction.RESPONSE:
                reason = (
                    f"Prazo de resposta (retorno solicitado) em {_fmt_date(earliest_date)}, "
                    f"{timing_text}."
                )
            else:
                reason = (
                    f"Prazo de {action_label} em {_fmt_date(earliest_date)}, "
                    f"{timing_text}."
                )
            return UrgencyDecision(
                level=UrgencyLevel.URGENT,
                reason=reason,
                basis_action=earliest_item.action,
                basis_date=earliest_date,
                past_deadlines=past_tuple,
                conflicting_deadlines=conflict_tuple,
            )

        if declared_urgency:
            return UrgencyDecision(
                level=UrgencyLevel.URGENT,
                reason="Urgência declarada explicitamente pelo remetente na mensagem.",
                basis_action=None,
                basis_date=None,
                past_deadlines=past_tuple,
                conflicting_deadlines=conflict_tuple,
            )

        return UrgencyDecision(
            level=UrgencyLevel.NORMAL,
            reason=(
                f"Prazo de {action_label} em {_fmt_date(earliest_date)}, "
                f"posterior ao dia seguinte ao recebimento ({_fmt_date(received_date)}), "
                f"sem urgência declarada."
            ),
            basis_action=earliest_item.action,
            basis_date=earliest_date,
            past_deadlines=past_tuple,
            conflicting_deadlines=conflict_tuple,
        )

    if declared_urgency:
        if past:
            past_desc = ", ".join(
                f"{_ACTION_LABELS[p.action]} em {_fmt_date(p.start_as_date)}"
                for p in past
                if p.start_as_date is not None
            )
            reason = (
                "Urgência declarada explicitamente pelo remetente na mensagem "
                f"(prazo inconsistente anterior ao recebimento desconsiderado: {past_desc})."
            )
        else:
            reason = "Urgência declarada explicitamente pelo remetente na mensagem."
        return UrgencyDecision(
            level=UrgencyLevel.URGENT,
            reason=reason,
            basis_action=None,
            basis_date=None,
            past_deadlines=past_tuple,
            conflicting_deadlines=conflict_tuple,
        )

    if past:
        past_desc = ", ".join(
            f"{_ACTION_LABELS[p.action]} em {_fmt_date(p.start_as_date)}"
            for p in past
            if p.start_as_date is not None
        )
        return UrgencyDecision(
            level=UrgencyLevel.UNDETERMINED,
            reason=(
                f"Inconsistência no prazo: {past_desc} é anterior à data de recebimento "
                f"({_fmt_date(received_date)}) e foi desconsiderado; sem outro prazo "
                "válido nem urgência declarada."
            ),
            basis_action=None,
            basis_date=None,
            past_deadlines=past_tuple,
            conflicting_deadlines=conflict_tuple,
        )

    if conflicting:
        return UrgencyDecision(
            level=UrgencyLevel.UNDETERMINED,
            reason=(
                "Prazo com referências de data em conflito (desconsiderado na "
                "classificação) e sem urgência declarada na mensagem."
            ),
            basis_action=None,
            basis_date=None,
            past_deadlines=past_tuple,
            conflicting_deadlines=conflict_tuple,
        )

    return UrgencyDecision(
        level=UrgencyLevel.UNDETERMINED,
        reason=(
            "Faltam dados de prazo válido para classificar a urgência e não "
            "há urgência declarada."
        ),
        basis_action=None,
        basis_date=None,
        past_deadlines=past_tuple,
        conflicting_deadlines=conflict_tuple,
    )


def classify_urgency(
    received_date: date,
    delivery_date_start: date | None = None,
    declared_urgency: bool = False,
    has_date_conflict: bool = False,
    *,
    response_deadline: date | None = None,
    document_availability_date_start: date | None = None,
    deadlines: Sequence[TriageDeadline] | None = None,
) -> tuple[UrgencyLevel, str]:
    """Classifica urgência e gera motivo padrão segundo as regras do RF04."""
    decision = evaluate_urgency(
        received_date=received_date,
        delivery_date_start=delivery_date_start,
        declared_urgency=declared_urgency,
        has_date_conflict=has_date_conflict,
        response_deadline=response_deadline,
        document_availability_date_start=document_availability_date_start,
        deadlines=deadlines,
    )
    return decision.level, decision.reason
