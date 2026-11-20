import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, or_, select

from ..agents.consultation.financial import (
    calculate_producer_financial_summary,
    resolve_period_bounds,
)
from ..agents.consultation.financial_formatting import (
    build_missing_exhaustive_financial_source_response,
    compose_deterministic_financial_summary_text,
    reconcile_financial_consultation_response,
)
from ..agents.consultation.schemas import (
    CitedSource,
    ConsultationGapOrDivergence,
    ConsultationInput,
    ConsultationResponse,
    ConsultationSourceItem,
)
from ..agents.consultation.schemas.producer_summary import (
    PlannedSupply,
    PlannedSupplySummary,
    PlannedSupplyTotal,
    ProducerSummaryResponse,
)
from ..helpers.units import are_compatible, convert_quantity, normalize_unit
from ..load.parsing import extract_unit, parse_date, parse_quantity
from ..models import Lot, Producer
from ..repositories.lot import LotRepository
from ..schemas.agent_integration import DocumentRetrievalContext, DocumentSourceProvider

LotKey = tuple[date, Decimal, str | None]


def _unit(unit: str | None) -> str | None:
    value = normalize_unit(unit)
    return {
        "maço": "maços",
        "caixa": "caixas",
        "litro": "litros",
        "dúzia": "dúzias",
        "duzia": "dúzias",
        "duzias": "dúzias",
    }.get(value, value)


def _historical_records(
    sources: Sequence[ConsultationSourceItem],
    producer_code: str,
) -> dict[LotKey, list[ConsultationSourceItem]]:
    records = defaultdict(dict)
    for source in sources:
        fields = source.record_fields or {}
        filename = source.document_name.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if (
            filename != "lotes.csv"
            or str(fields.get("produtor_id", "")).strip().upper()
            != producer_code.upper()
        ):
            continue
        record_id = str(fields.get("lote_id") or source.record_id or "").strip()
        if not record_id or not str(fields.get("produto") or "").strip():
            continue
        observation = str(fields.get("observacao") or "")
        try:
            quantity = parse_quantity(str(fields["quantidade_kg"]))
            delivery = parse_date(str(fields["data_entrega"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if not quantity.is_finite() or quantity <= 0:
            continue
        key = delivery, quantity, _unit(extract_unit(observation))
        records[key].setdefault(record_id, source)
    return {key: list(matches.values()) for key, matches in records.items()}


def summarize_planned_supplies(
    lots: Sequence[Lot],
    sources: Sequence[ConsultationSourceItem],
    *,
    producer_code: str,
) -> PlannedSupplySummary:
    records = _historical_records(sources, producer_code)
    historical_counts: dict[LotKey, int] = defaultdict(int)
    for lot in lots:
        if lot.item_id is None:
            historical_counts[lot.delivery_date, lot.quantity, _unit(lot.unit)] += 1
    supplies = []
    pending = []
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for lot in lots:
        unit = _unit(lot.unit)
        if lot.item_id is not None:
            supply = PlannedSupply(
                lot_id=lot.id,
                producer_id=lot.producer_id,
                product=lot.item.product.name,
                delivery_date=lot.delivery_date,
                quantity=lot.quantity,
                unit=unit,
                origin="operacional",
                order_id=lot.item.order_id,
                item_id=lot.item_id,
            )
        else:
            key = lot.delivery_date, lot.quantity, unit
            matches = records.get(key, [])
            if len(matches) != 1 or historical_counts[key] != 1:
                pending.append(
                    ConsultationGapOrDivergence(
                        kind="divergencia" if matches else "lacuna",
                        description=(
                            f"Lote histórico {lot.id}, entrega em {lot.delivery_date:%d/%m/%Y}: "
                            "não foi possível vincular um único registro de lotes.csv."
                        ),
                        source_ids=[source.source_id for source in matches],
                    )
                )
                continue
            source = matches[0]
            fields = source.record_fields
            supply = PlannedSupply(
                lot_id=lot.id,
                producer_id=lot.producer_id,
                product=str(fields["produto"]).strip(),
                delivery_date=lot.delivery_date,
                quantity=lot.quantity,
                unit=unit,
                origin="historico",
                document_source_id=source.source_id,
                record_id=str(fields.get("lote_id") or source.record_id).strip(),
                observation=str(fields.get("observacao") or "").strip() or None,
            )
        if _is_ambiguous_observation(supply.observation):
            supply = supply.model_copy(update={"unit": None})
        supplies.append(supply)
        if not supply.unit or not supply.quantity.is_finite() or supply.quantity <= 0:
            pending.append(
                ConsultationGapOrDivergence(
                    kind="unidade_ambigua",
                    description=f"{supply.record_id or supply.lot_id}: quantidade ou unidade a esclarecer"
                    + (f" («{supply.observation}»)." if supply.observation else "."),
                    source_ids=[supply.document_source_id]
                    if supply.document_source_id
                    else [],
                )
            )
            continue
        unit_for_total = "kg" if are_compatible(supply.unit, "kg") else supply.unit
        totals[supply.product.casefold(), unit_for_total] += convert_quantity(
            supply.quantity,
            supply.unit,
            unit_for_total,
        )
    names = {supply.product.casefold(): supply.product for supply in supplies}
    return PlannedSupplySummary(
        supplies=sorted(
            supplies,
            key=lambda row: (
                row.delivery_date,
                row.product.casefold(),
                str(row.lot_id),
            ),
        ),
        totals=[
            PlannedSupplyTotal(product=names[product], quantity=quantity, unit=unit)
            for (product, unit), quantity in sorted(totals.items())
        ],
        pending=pending,
    )


def _is_ambiguous_observation(observation: str | None) -> bool:
    if not observation:
        return False
    return bool(
        re.search(
            r"\b(?:agregad\w*|ambigu\w*|ambígu\w*|total\s+(?:de|para|entre)|"
            r"entre\s+\d+|\d+\s*(?:a|ou|[-–])\s*\d+)\b",
            observation,
            flags=re.IGNORECASE,
        )
    )


def _render_supplies(result: PlannedSupplySummary) -> str:
    lines = ["Fornecimentos previstos"]
    if not result.supplies:
        if result.pending:
            lines.append(
                "Nenhum fornecimento pôde ser detalhado no período consultado."
            )
        else:
            lines.append(
                "Não há fornecimentos previstos na base para o período consultado."
            )
    for supply in result.supplies:
        reference = (
            f"lotes.csv — {supply.record_id}"
            if supply.record_id
            else f"alocação {supply.lot_id}, pedido {supply.order_id}, item {supply.item_id}"
        )
        quantity = (
            f"{_quantity_text(supply.quantity)} {_unit_label(supply.unit)}"
            if supply.unit
            else "quantidade ou unidade a esclarecer"
        )
        lines.append(
            f"- {supply.delivery_date:%d/%m/%Y}: {supply.product}, {quantity} ({reference})."
        )
    if result.totals:
        lines.append("Totais dos fornecimentos identificados por produto e unidade")
        lines.extend(
            f"- {total.product}: {_quantity_text(total.quantity)} {_unit_label(total.unit)}."
            for total in result.totals
        )
    if result.pending:
        lines.append("Pendências dos fornecimentos")
        lines.extend(f"- {gap.description}" for gap in result.pending)
    return "\n".join(lines)


def _quantity_text(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def _unit_label(unit: str) -> str:
    return "unidades" if unit == "un" else unit


class ProducerSummaryService:
    def __init__(
        self, lots: LotRepository, source_provider: DocumentSourceProvider
    ) -> None:
        self.lots = lots
        self.source_provider = source_provider

    async def answer_producer_summary(
        self,
        producer: str,
        *,
        session_id: UUID,
        reference_date: date,
        period: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> ProducerSummaryResponse:
        target = producer.strip().lower()
        if not target:
            raise ValueError("Informe o código ou o nome completo do produtor.")
        producers = list(
            await self.lots.session.scalars(
                select(Producer)
                .where(
                    or_(
                        func.lower(Producer.code) == target,
                        func.lower(Producer.name) == target,
                    )
                )
                .limit(2)
            )
        )
        if len(producers) != 1:
            raise ValueError(
                "Informe um código de produtor cadastrado que identifique um único produtor."
            )
        selected = producers[0]
        if (period_start is None) != (period_end is None):
            raise ValueError("Informe as duas datas do período.")
        start, end = resolve_period_bounds(
            period,
            period_start=period_start,
            period_end=period_end,
            fallback_reference_date=reference_date,
        )
        retrieved = await self.source_provider.retrieve_sources(
            DocumentRetrievalContext(
                session_id=session_id,
                flow="consultation",
                reference_date=reference_date,
                query_text=f"Resumo de {selected.code}: registros históricos de lotes.csv por data de entrega de {start} a {end} e financeiro.csv.",
                producer_id=selected.code,
                period_start=start,
                period_end=end,
                financial_reference_date=reference_date,
            )
        )
        lots = await self.lots.list_planned_supplies(selected.id, start, end)
        supplies = summarize_planned_supplies(
            lots, retrieved.sources, producer_code=selected.code
        )

        records = retrieved.financial_records
        if records is None:
            calculation = None
            financial = build_missing_exhaustive_financial_source_response(
                reference_date.isoformat()
            )
        else:
            calculation = calculate_producer_financial_summary(
                selected.code,
                reference_date=reference_date,
                period_start=start,
                period_end=end,
                financial_records=records,
            )
            financial = reconcile_financial_consultation_response(
                ConsultationResponse(
                    answer=compose_deterministic_financial_summary_text(calculation),
                    reference_date_used=reference_date,
                ),
                calculation,
                ConsultationInput(
                    question=f"Resumo financeiro de {selected.code}",
                    reference_date=reference_date,
                    financial_records=records,
                ),
            )
        historical_ids = {
            supply.document_source_id
            for supply in supplies.supplies
            if supply.document_source_id
        }
        historical_ids.update(
            source_id for gap in supplies.pending for source_id in gap.source_ids
        )
        historical_citations = {
            source.source_id: CitedSource(
                source_id=source.source_id,
                document_id=source.document_id,
                document_name=source.document_name,
                reference_label=source.record_id or source.reference_label,
            )
            for source in retrieved.sources
            if source.source_id in historical_ids
        }
        title = (
            f"Resumo de {selected.name} ({selected.code}) — "
            f"{start:%d/%m/%Y} a {end:%d/%m/%Y} — referência {reference_date:%d/%m/%Y}"
        )
        return ProducerSummaryResponse(
            answer=f"{title}\n\n{financial.answer}\n\n{_render_supplies(supplies)}",
            reference_date_used=reference_date,
            producer_name=selected.name,
            producer_code=selected.code,
            period_start=start,
            period_end=end,
            financial=calculation,
            planned_supplies=supplies,
            source_ids=[*financial.source_ids, *historical_citations],
            cited_sources=[*financial.cited_sources, *historical_citations.values()],
            gaps_and_divergences=[*financial.gaps_and_divergences, *supplies.pending],
            has_sufficient_data=(
                records is not None
                and not supplies.pending
                and (financial.has_sufficient_data or bool(supplies.supplies))
            ),
        )
