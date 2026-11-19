from datetime import date

from .reconciliation import reconcile_consultation_sources
from .schemas.financial import FinancialCalculationBucket, FinancialSummaryCalculation
from .schemas.input import ConsultationInput
from .schemas.response import ConsultationGapOrDivergence, ConsultationResponse


def _format_br_date(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return parsed.strftime("%d/%m/%Y")


def _format_tx_refs(bucket: FinancialCalculationBucket) -> str:
    if not bucket.transaction_ids:
        return "sem registros encontrados"
    joined = ", ".join(bucket.transaction_ids)
    return f"{joined} ({bucket.source_document})"


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
    lines.extend(
        [
            f"periodo: {calculation.period_start} a {calculation.period_end}",
            f"data_referencia: {calculation.reference_date} ({_format_br_date(calculation.reference_date)})",
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
    """Gera o texto de resumo financeiro preservando todos os valores e citações da ferramenta."""
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


def reconcile_financial_consultation_response(
    response: ConsultationResponse,
    calculation: FinancialSummaryCalculation,
    payload: ConsultationInput,
) -> ConsultationResponse:
    """Garante preservação dos valores calculados (RNF04) e citação dos registros financeiros (RNF06)."""
    if not payload.sources:
        return reconcile_consultation_sources(response, payload)

    if not calculation.has_any_records:
        deterministic_text = compose_deterministic_financial_summary_text(calculation)
        empty_calc_response = ConsultationResponse(
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
        return reconcile_consultation_sources(empty_calc_response, payload)

    merged_source_ids = list(calculation.all_source_ids)
    for sid in response.source_ids:
        if sid in calculation.all_source_ids and sid not in merged_source_ids:
            merged_source_ids.append(sid)

    required_tokens: list[str] = [calculation.source_document, *calculation.all_transaction_ids]
    for bucket in (
        calculation.sales_in_period,
        calculation.registered_payments_in_period,
        calculation.pending_overdue,
        calculation.pending_upcoming,
    ):
        if bucket.has_records:
            required_tokens.append(bucket.formatted_total)

    answer_text = response.answer
    missing_token = any(token not in answer_text for token in required_tokens)
    has_missing_bucket = any(
        not b.has_records
        for b in (
            calculation.sales_in_period,
            calculation.registered_payments_in_period,
            calculation.pending_total,
        )
    )
    mentions_absence = any(
        marker in answer_text.lower()
        for marker in ("não foram encontrados", "nao foram encontrados", "sem registros", "ausência", "nenhum pagamento")
    )

    if missing_token or (has_missing_bucket and not mentions_absence):
        answer_text = compose_deterministic_financial_summary_text(calculation)

    enriched = ConsultationResponse(
        answer=answer_text,
        reference_date_used=calculation.reference_date,
        source_ids=merged_source_ids,
        cited_sources=response.cited_sources,
        gaps_and_divergences=response.gaps_and_divergences,
        has_sufficient_data=True,
    )
    return reconcile_consultation_sources(enriched, payload)
