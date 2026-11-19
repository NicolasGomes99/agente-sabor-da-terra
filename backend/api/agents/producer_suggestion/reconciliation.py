from collections.abc import Sequence
from datetime import date

from ..consultation.schemas.input import ConsultationSourceItem
from ..consultation.schemas.response import CitedSource
from .evaluation import compose_deterministic_suggestion_summary
from .schemas.input import BalanceStatus, OrderToolContract
from .schemas.response import (
    AlternativeProductSuggestion,
    OrderItemSuggestionResult,
    ProducerSuggestionResponse,
)


def _filter_source_ids(
    source_ids: Sequence[str],
    source_map: dict[str, ConsultationSourceItem],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for sid in source_ids:
        cleaned = sid.strip()
        if cleaned in source_map and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for val in values:
        cleaned = val.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return ordered


def reconcile_producer_suggestion_response(
    raw_response: ProducerSuggestionResponse,
    baseline: ProducerSuggestionResponse,
    *,
    order: OrderToolContract,
    sources: Sequence[ConsultationSourceItem],
) -> ProducerSuggestionResponse:
    """Reconcilia a saída do agente ADK garantindo invariantes operacionais e citações (#25)."""
    source_map = {src.source_id: src for src in sources}
    raw_items_by_id = {
        item.order_item_id: item for item in raw_response.item_suggestions
    }

    reconciled_items: list[OrderItemSuggestionResult] = []
    for base_item in baseline.item_suggestions:
        raw_item = raw_items_by_id.get(base_item.order_item_id)
        excluded_ids = {excl.producer_id for excl in base_item.excluded_producers}
        excluded_codes = {excl.producer_code.upper() for excl in base_item.excluded_producers}

        reconciled_candidates = []
        raw_cands_by_id = (
            {c.producer_id: c for c in raw_item.candidates} if raw_item else {}
        )
        raw_cands_by_code = (
            {c.producer_code.upper(): c for c in raw_item.candidates} if raw_item else {}
        )

        for base_cand in base_item.candidates:
            if (
                base_cand.producer_id in excluded_ids
                or base_cand.producer_code.upper() in excluded_codes
            ):
                continue
            raw_cand = raw_cands_by_id.get(
                base_cand.producer_id
            ) or raw_cands_by_code.get(base_cand.producer_code.upper())

            merged_pendings = list(base_cand.pending_confirmations)
            merged_sources = list(base_cand.source_ids)
            if raw_cand is not None:
                merged_pendings.extend(raw_cand.pending_confirmations)
                merged_sources.extend(raw_cand.source_ids)

            reconciled_candidates.append(
                base_cand.model_copy(
                    update={
                        "availability_confirmed": False,
                        "pending_confirmations": _dedupe_strings(merged_pendings),
                        "source_ids": _filter_source_ids(merged_sources, source_map),
                    }
                )
            )

        reconciled_excluded = [
            excl.model_copy(
                update={
                    "source_ids": _filter_source_ids(excl.source_ids, source_map),
                }
            )
            for excl in base_item.excluded_producers
        ]

        validated_alternatives: list[AlternativeProductSuggestion] = []
        if (
            raw_item is not None
            and base_item.balance_status != BalanceStatus.FULLY_ALLOCATED
        ):
            for alt in raw_item.alternative_suggestions:
                if not alt.alternative_product_name.strip():
                    continue
                alt_pendings = _dedupe_strings(
                    [
                        *alt.pending_confirmations,
                        (
                            f"Decisão do funcionário necessária para aceitar a substituição "
                            f"de '{base_item.product_name}' por '{alt.alternative_product_name}' "
                            "e confirmar disponibilidade para quantidade e data."
                        ),
                    ]
                )
                validated_alternatives.append(
                    AlternativeProductSuggestion(
                        replaces_order_item_id=base_item.order_item_id,
                        replaces_product_name=base_item.product_name,
                        alternative_product_name=alt.alternative_product_name.strip(),
                        reason=alt.reason.strip(),
                        candidate_producers_summary=alt.candidate_producers_summary.strip(),
                        requires_staff_approval=True,
                        pending_confirmations=alt_pendings,
                        source_ids=_filter_source_ids(alt.source_ids, source_map),
                    )
                )

        reconciled_items.append(
            base_item.model_copy(
                update={
                    "candidates": reconciled_candidates,
                    "excluded_producers": reconciled_excluded,
                    "alternative_suggestions": validated_alternatives,
                }
            )
        )

    if order.cancelled or order.needs_item_structuring:
        rebuilt_summary = baseline.summary
    else:
        rebuilt_summary = compose_deterministic_suggestion_summary(
            order=order,
            window_start=date.fromisoformat(baseline.evaluated_delivery_start),
            window_end=date.fromisoformat(baseline.evaluated_delivery_end),
            exact_used=baseline.exact_delivery_date_used,
            reference_date=date.fromisoformat(baseline.reference_date_used),
            item_results=reconciled_items,
        )

    collected_source_ids: list[str] = []
    for item in reconciled_items:
        for cand in item.candidates:
            collected_source_ids.extend(cand.source_ids)
        for excl in item.excluded_producers:
            collected_source_ids.extend(excl.source_ids)
        for alt in item.alternative_suggestions:
            collected_source_ids.extend(alt.source_ids)
    valid_source_ids = _filter_source_ids(collected_source_ids, source_map)

    existing_cited_by_id = {
        c.source_id: c
        for c in raw_response.cited_sources
        if c.source_id in source_map
    }
    rebuilt_cited = [
        CitedSource(
            source_id=sid,
            document_id=source_map[sid].document_id,
            document_name=source_map[sid].document_name,
            reference_label=source_map[sid].reference_label,
            supporting_excerpt=(
                existing_cited_by_id[sid].supporting_excerpt
                if sid in existing_cited_by_id
                else None
            ),
        )
        for sid in valid_source_ids
    ]

    return ProducerSuggestionResponse(
        order_id=baseline.order_id,
        buyer=baseline.buyer,
        reference_date_used=baseline.reference_date_used,
        evaluated_delivery_start=baseline.evaluated_delivery_start,
        evaluated_delivery_end=baseline.evaluated_delivery_end,
        exact_delivery_date_used=baseline.exact_delivery_date_used,
        summary=rebuilt_summary,
        item_suggestions=reconciled_items,
        source_ids=valid_source_ids,
        cited_sources=rebuilt_cited,
        general_pending_confirmations=_dedupe_strings(
            [
                *baseline.general_pending_confirmations,
                *raw_response.general_pending_confirmations,
            ]
        ),
    )
