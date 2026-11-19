from collections.abc import Sequence
from datetime import date
from typing import Any

from .financial import FINANCIAL_SOURCE_FILENAME, to_consultation_source_item
from .reconciliation import reconcile_consultation_sources
from .schemas.financial import FinancialCalculationBucket, FinancialSummaryCalculation
from .schemas.input import ConsultationInput, ConsultationSourceItem
from .schemas.response import ConsultationGapOrDivergence, ConsultationResponse


def _format_br_date(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return parsed.strftime("%d/%m/%Y")


def _format_tx_refs(bucket: FinancialCalculationBucket) -> str:
    if not bucket.transaction_ids:
        return "sem registros encontrados"
    return ", ".join(
        f"{bucket.source_document} - {tx_id}" for tx_id in bucket.transaction_ids
    )


def format_financial_calculation_prompt_block(
    calculation: FinancialSummaryCalculation,
) -> str:
    """Formata o resultado determinístico da ferramenta financeira para o prompt do agente."""
    lines = [
        "<calculo_financeiro_ferramenta>",
        f"produtor_id: {calculation.producer_id}",
    ]
    if calculation.producer_name:
        lines.append(f"produtor_nome: {calculation.producer_name}")
    if calculation.is_ambiguous_producer:
        lines.append("produtor_ambiguo: true")
        if calculation.clarification_message:
            lines.append(f"esclarecimento: {calculation.clarification_message}")
        lines.append("</calculo_financeiro_ferramenta>")
        return "\n".join(lines)

    lines.extend(
        [
            f"periodo: {calculation.period_start} a {calculation.period_end}",
            (
                f"data_referencia: {calculation.reference_date} "
                f"({_format_br_date(calculation.reference_date)})"
            ),
            f"documento_origem: {calculation.source_document}",
            (
                f"vendas_no_periodo: {calculation.sales_in_period.formatted_total} "
                f"| possui_registros={calculation.sales_in_period.has_records} "
                f"| transacoes={calculation.sales_in_period.transaction_ids}"
            ),
            (
                f"pagamentos_registrados_no_periodo: "
                f"{calculation.registered_payments_in_period.formatted_total} "
                f"| possui_registros={calculation.registered_payments_in_period.has_records} "
                f"| transacoes={calculation.registered_payments_in_period.transaction_ids}"
            ),
            (
                f"pendencias_vencidas: {calculation.pending_overdue.formatted_total} "
                f"| possui_registros={calculation.pending_overdue.has_records} "
                f"| vencimentos={calculation.pending_overdue.due_dates} "
                f"| transacoes={calculation.pending_overdue.transaction_ids}"
            ),
            (
                f"pendencias_a_vencer: {calculation.pending_upcoming.formatted_total} "
                f"| possui_registros={calculation.pending_upcoming.has_records} "
                f"| vencimentos={calculation.pending_upcoming.due_dates} "
                f"| transacoes={calculation.pending_upcoming.transaction_ids}"
            ),
            "</calculo_financeiro_ferramenta>",
        ]
    )
    return "\n".join(lines)


def compose_deterministic_financial_summary_text(
    calculation: FinancialSummaryCalculation,
) -> str:
    """Gera o texto de resumo financeiro preservando cada cálculo, valor e transação."""
    if calculation.is_ambiguous_producer:
        if calculation.clarification_message:
            return calculation.clarification_message
        candidates_desc = ", ".join(
            f"{c.producer_id} ({c.producer_name})" if c.producer_name else c.producer_id
            for c in calculation.matching_producers
        )
        return (
            f"Foram encontrados múltiplos produtores correspondentes a "
            f"'{calculation.producer_id}' em {calculation.source_document}: "
            f"{candidates_desc}. Informe o código do produtor ou o nome completo "
            "para gerar o resumo financeiro."
        )

    producer_label = (
        f"{calculation.producer_name} ({calculation.producer_id})"
        if calculation.producer_name
        else calculation.producer_id
    )
    ref_br = _format_br_date(calculation.reference_date)
    start_br = _format_br_date(calculation.period_start)
    end_br = _format_br_date(calculation.period_end)

    if not calculation.has_any_records:
        return (
            f"Considerando a data de referência {ref_br} ({calculation.reference_date}) "
            f"e o período de {start_br} a {end_br}, não foram encontrados registros "
            f"financeiros para o produtor {producer_label} na base consultada "
            f"({calculation.source_document})."
        )

    parts = [
        (
            f"Resumo financeiro de {producer_label} no período de {start_br} a {end_br}, "
            f"com data de referência em {ref_br} ({calculation.reference_date}):"
        )
    ]

    if calculation.sales_in_period.has_records:
        parts.append(
            f"- Vendas no período: {calculation.sales_in_period.formatted_total}, "
            f"sustentadas por {_format_tx_refs(calculation.sales_in_period)}."
        )
    else:
        parts.append(
            "- Vendas no período: não foram encontrados registros de vendas para o "
            "período solicitado na base."
        )

    if calculation.registered_payments_in_period.has_records:
        parts.append(
            f"- Pagamentos registrados no período (informação registrada na base, "
            f"sem constituir comprovação de repasse bancário): "
            f"{calculation.registered_payments_in_period.formatted_total}, "
            f"sustentados por {_format_tx_refs(calculation.registered_payments_in_period)}."
        )
    else:
        parts.append(
            "- Pagamentos registrados no período: não foram encontrados registros "
            "de pagamentos no período solicitado na base."
        )

    if calculation.pending_upcoming.has_records:
        due_br_list = [
            f"{_format_br_date(d)} ({d})" for d in calculation.pending_upcoming.due_dates
        ]
        due_str = ", ".join(due_br_list)
        due_clause = f" em {due_str}" if due_str else ""
        parts.append(
            f"- Pendências a vencer{due_clause}: "
            f"{calculation.pending_upcoming.formatted_total}, "
            f"sustentadas por {_format_tx_refs(calculation.pending_upcoming)}."
        )

    if calculation.pending_overdue.has_records:
        overdue_br_list = [
            f"{_format_br_date(d)} ({d})" for d in calculation.pending_overdue.due_dates
        ]
        overdue_str = ", ".join(overdue_br_list)
        overdue_clause = f" (vencimento em {overdue_str})" if overdue_str else ""
        parts.append(
            f"- Pendências vencidas{overdue_clause}: "
            f"{calculation.pending_overdue.formatted_total}, "
            f"sustentadas por {_format_tx_refs(calculation.pending_overdue)}."
        )

    if not calculation.pending_total.has_records:
        parts.append(
            "- Pendências financeiras na data de referência: não foram encontrados "
            "registros de pendências em aberto na base."
        )

    return "\n".join(parts)


def build_missing_exhaustive_financial_source_response(
    reference_date_iso: str,
) -> ConsultationResponse:
    """Resposta determinística quando não há garantia de recuperação exaustiva de financeiro.csv."""
    ref_br = _format_br_date(reference_date_iso)
    message = (
        f"Considerando a data de referência {ref_br} ({reference_date_iso}), "
        f"não é possível calcular o resumo financeiro completo porque a coleção "
        f"exaustiva de registros de {FINANCIAL_SOURCE_FILENAME} não foi disponibilizada "
        f"para a ferramenta financeira (apenas resultados parciais de busca documental "
        f"não garantem a inclusão de todas as transações elegíveis)."
    )
    return ConsultationResponse(
        answer=message,
        reference_date_used=reference_date_iso,
        source_ids=[],
        cited_sources=[],
        gaps_and_divergences=[
            ConsultationGapOrDivergence(
                kind="lacuna",
                description=(
                    f"Recuperação exaustiva de {FINANCIAL_SOURCE_FILENAME} ausente; "
                    "cálculo financeiro bloqueado para evitar totais parciais."
                ),
                source_ids=[],
            )
        ],
        has_sufficient_data=False,
    )


def build_missing_financial_parameters_response(
    reference_date_iso: str,
    *,
    reason: str | None = None,
) -> ConsultationResponse:
    """Resposta determinística pedindo esclarecimento quando não há cálculo financeiro válido."""
    ref_br = _format_br_date(reference_date_iso)
    detail = (
        reason
        or (
            "Não foi possível identificar de forma inequívoca os parâmetros necessários "
            "(código ou nome completo do produtor, período e data de referência) para "
            f"executar o cálculo financeiro determinístico em {FINANCIAL_SOURCE_FILENAME}."
        )
    )
    message = (
        f"Considerando a data de referência {ref_br} ({reference_date_iso}), "
        f"{detail} Informe o código ou nome completo do produtor, o período e, "
        "se aplicável, a data de referência desejada para gerar o resumo financeiro."
    )
    return ConsultationResponse(
        answer=message,
        reference_date_used=reference_date_iso,
        source_ids=[],
        cited_sources=[],
        gaps_and_divergences=[
            ConsultationGapOrDivergence(
                kind="lacuna",
                description=detail,
                source_ids=[],
            )
        ],
        has_sufficient_data=False,
    )


def _merge_reconciliation_payload(
    payload: ConsultationInput,
    exhaustive_financial_records: Sequence[ConsultationSourceItem | Any] | None,
    *,
    calculation_reference_date: str,
) -> ConsultationInput:
    merged_sources: list[ConsultationSourceItem] = []
    seen_ids: set[str] = set()

    for raw_record in exhaustive_financial_records or []:
        normalized = to_consultation_source_item(raw_record)
        if normalized is not None and normalized.source_id not in seen_ids:
            seen_ids.add(normalized.source_id)
            merged_sources.append(normalized)

    for src in payload.sources:
        if src.source_id not in seen_ids:
            seen_ids.add(src.source_id)
            merged_sources.append(src)

    return payload.model_copy(
        update={
            "sources": merged_sources,
            "reference_date": calculation_reference_date,
        }
    )


def reconcile_financial_consultation_response(
    response: ConsultationResponse,
    calculation: FinancialSummaryCalculation,
    payload: ConsultationInput,
    *,
    exhaustive_financial_records: Sequence[ConsultationSourceItem | Any] | None = None,
) -> ConsultationResponse:
    """Preserva exatamente cada cálculo, valor e transação financeira (RF08, RNF04, RNF06)."""
    effective_payload = _merge_reconciliation_payload(
        payload,
        exhaustive_financial_records=(
            exhaustive_financial_records
            if exhaustive_financial_records is not None
            else payload.financial_records
        ),
        calculation_reference_date=calculation.reference_date,
    )

    if calculation.is_ambiguous_producer:
        clarification_text = compose_deterministic_financial_summary_text(calculation)
        return ConsultationResponse(
            answer=clarification_text,
            reference_date_used=calculation.reference_date,
            source_ids=[],
            cited_sources=[],
            gaps_and_divergences=[
                ConsultationGapOrDivergence(
                    kind="lacuna",
                    description=clarification_text,
                    source_ids=[],
                )
            ],
            has_sufficient_data=False,
        )

    if not calculation.has_any_records:
        deterministic_text = compose_deterministic_financial_summary_text(calculation)
        return ConsultationResponse(
            answer=deterministic_text,
            reference_date_used=calculation.reference_date,
            source_ids=[],
            cited_sources=[],
            gaps_and_divergences=[
                ConsultationGapOrDivergence(
                    kind="lacuna",
                    description=(
                        f"Não foram encontrados registros em {calculation.source_document} "
                        f"para o produtor {calculation.producer_id} no período e data de "
                        f"referência consultados."
                    ),
                    source_ids=[],
                )
            ],
            has_sufficient_data=False,
        )

    # Usa o formatador determinístico para preservar estritamente a associação entre
    # cada categoria financeira, seu valor calculado e as transações que o sustentam.
    deterministic_answer = compose_deterministic_financial_summary_text(calculation)
    allowed_source_ids = set(calculation.all_source_ids)
    filtered_cited_sources = [
        cited for cited in response.cited_sources if cited.source_id in allowed_source_ids
    ]
    filtered_gaps = [
        ConsultationGapOrDivergence(
            kind=gap.kind,
            description=gap.description,
            source_ids=[sid for sid in gap.source_ids if sid in allowed_source_ids],
        )
        for gap in response.gaps_and_divergences
    ]

    enriched = ConsultationResponse(
        answer=deterministic_answer,
        reference_date_used=calculation.reference_date,
        source_ids=list(calculation.all_source_ids),
        cited_sources=filtered_cited_sources,
        gaps_and_divergences=filtered_gaps,
        has_sufficient_data=True,
    )
    return reconcile_consultation_sources(enriched, effective_payload)
