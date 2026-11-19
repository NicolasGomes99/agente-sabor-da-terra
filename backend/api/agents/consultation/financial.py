import calendar
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..config import to_pernambuco_date
from .schemas.financial import (
    FinancialCalculationBucket,
    FinancialSummaryCalculation,
    format_brl_currency,
)
from .schemas.input import ConsultationSourceItem


@dataclass(frozen=True)
class _ParsedFinancialRow:
    source_id: str
    document_name: str
    transaction_id: str
    producer_id: str
    producer_name: str | None
    transaction_type: str
    amount: Decimal
    transaction_date: date
    due_date: date | None
    payment_date: date | None


def _parse_optional_date(raw: Any) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return to_pernambuco_date(text)


def _parse_content_kv(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for sep in (";", ",", "\n"):
        if sep in content and "=" in content:
            for part in content.split(sep):
                if "=" in part:
                    k, v = part.split("=", maxsplit=1)
                    fields[k.strip()] = v.strip()
            if fields:
                return fields
    return fields


def _extract_financial_row(item: ConsultationSourceItem | Any) -> _ParsedFinancialRow | None:
    if isinstance(item, ConsultationSourceItem):
        source_id = item.source_id
        document_name = item.document_name
        raw_fields = dict(item.record_fields) if item.record_fields else _parse_content_kv(item.content)
        fallback_tx_id = item.record_id or item.reference_label
    elif isinstance(item, dict):
        source_id = str(item.get("source_id") or item.get("id") or "")
        document_name = str(item.get("document_name") or "financeiro.csv")
        raw_fields = dict(item.get("record_fields") or _parse_content_kv(str(item.get("content") or "")))
        fallback_tx_id = item.get("record_id") or item.get("reference_label") or raw_fields.get("id_transacao")
    else:
        source_id = str(getattr(item, "source_id", None) or getattr(item, "id", ""))
        doc_obj = getattr(item, "document", None)
        document_name = str(
            getattr(item, "document_name", None)
            or getattr(doc_obj, "original_filename", None)
            or "financeiro.csv"
        )
        record_fields = getattr(item, "record_fields", None)
        content_str = str(getattr(item, "content", "") or "")
        raw_fields = dict(record_fields) if record_fields else _parse_content_kv(content_str)
        fallback_tx_id = getattr(item, "record_id", None) or getattr(item, "reference_label", None)

    tx_id = str(raw_fields.get("id_transacao") or fallback_tx_id or "").strip()
    prod_id = str(raw_fields.get("produtor_id") or "").strip()
    raw_amount = raw_fields.get("valor_total")
    raw_tx_date = raw_fields.get("data") or raw_fields.get("data_transacao")

    if not tx_id or not prod_id or raw_amount is None or not raw_tx_date:
        return None

    try:
        amount = Decimal(str(raw_amount).strip())
        tx_date = to_pernambuco_date(str(raw_tx_date).strip())
    except Exception:  # noqa: BLE001
        return None

    return _ParsedFinancialRow(
        source_id=source_id or tx_id,
        document_name=document_name or "financeiro.csv",
        transaction_id=tx_id,
        producer_id=prod_id,
        producer_name=(str(raw_fields.get("produtor_nome")).strip() if raw_fields.get("produtor_nome") else None),
        transaction_type=str(raw_fields.get("tipo") or "venda").strip().lower(),
        amount=amount,
        transaction_date=tx_date,
        due_date=_parse_optional_date(raw_fields.get("data_vencimento")),
        payment_date=_parse_optional_date(raw_fields.get("data_pagamento")),
    )


def resolve_period_bounds(
    period: str | None = None,
    *,
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    fallback_reference_date: date | None = None,
) -> tuple[date, date]:
    if period_start is not None and period_end is not None:
        start = to_pernambuco_date(period_start)
        end = to_pernambuco_date(period_end)
        if end < start:
            raise ValueError("period_end must be greater than or equal to period_start.")
        return start, end

    if period:
        cleaned = period.strip()
        if len(cleaned) == 7 and cleaned[4] == "-":
            year, month = int(cleaned[:4]), int(cleaned[5:7])
        elif len(cleaned) == 7 and cleaned[2] == "/":
            month, year = int(cleaned[:2]), int(cleaned[3:7])
        else:
            single = to_pernambuco_date(cleaned)
            return single, single
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    if fallback_reference_date is not None:
        last_day = calendar.monthrange(
            fallback_reference_date.year,
            fallback_reference_date.month,
        )[1]
        return (
            date(fallback_reference_date.year, fallback_reference_date.month, 1),
            date(fallback_reference_date.year, fallback_reference_date.month, last_day),
        )

    raise ValueError("Either (period_start, period_end) or period must be provided.")


def _build_bucket(rows: list[_ParsedFinancialRow]) -> FinancialCalculationBucket:
    if not rows:
        return FinancialCalculationBucket()

    total = sum((r.amount for r in rows), Decimal("0.00"))
    tx_ids: list[str] = []
    src_ids: list[str] = []
    due_dates: list[str] = []
    pay_dates: list[str] = []

    for r in rows:
        if r.transaction_id not in tx_ids:
            tx_ids.append(r.transaction_id)
        if r.source_id not in src_ids:
            src_ids.append(r.source_id)
        if r.due_date is not None:
            iso_due = r.due_date.isoformat()
            if iso_due not in due_dates:
                due_dates.append(iso_due)
        if r.payment_date is not None:
            iso_pay = r.payment_date.isoformat()
            if iso_pay not in pay_dates:
                pay_dates.append(iso_pay)

    return FinancialCalculationBucket(
        total_amount=total,
        formatted_total=format_brl_currency(total),
        transaction_ids=tx_ids,
        source_ids=src_ids,
        due_dates=due_dates,
        payment_dates=pay_dates,
        source_document=rows[0].document_name,
        has_records=True,
    )


def calculate_producer_financial_summary(
    producer: str,
    *,
    reference_date: date | datetime | str,
    sources: Sequence[ConsultationSourceItem | Any],
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    period: str | None = None,
) -> FinancialSummaryCalculation:
    """Calcula vendas, pagamentos registrados e pendências de um produtor conforme RF08."""
    target = producer.strip()
    if not target:
        raise ValueError("producer must not be blank.")

    ref_date = to_pernambuco_date(reference_date)
    start_date, end_date = resolve_period_bounds(
        period,
        period_start=period_start,
        period_end=period_end,
        fallback_reference_date=ref_date,
    )

    is_code_target = len(target) >= 2 and target[0].upper() == "P" and target[1:].isdigit()
    producer_rows: list[_ParsedFinancialRow] = []
    for src in sources:
        parsed = _extract_financial_row(src)
        if parsed is None or parsed.transaction_type != "venda":
            continue
        id_match = parsed.producer_id.upper() == target.upper()
        name_match = (
            False
            if is_code_target
            else bool(
                parsed.producer_name and target.lower() in parsed.producer_name.lower()
            )
        )
        if id_match or name_match:
            producer_rows.append(parsed)

    sales_rows = [
        r
        for r in producer_rows
        if start_date <= r.transaction_date <= end_date
        and r.transaction_date <= ref_date
    ]
    payment_rows = [
        r
        for r in producer_rows
        if r.payment_date is not None
        and start_date <= r.payment_date <= end_date
        and r.payment_date <= ref_date
    ]
    pending_rows = [
        r
        for r in producer_rows
        if r.transaction_date <= ref_date
        and (r.payment_date is None or r.payment_date > ref_date)
    ]
    overdue_rows = [
        r
        for r in pending_rows
        if r.due_date is not None and r.due_date < ref_date
    ]
    upcoming_rows = [
        r
        for r in pending_rows
        if r.due_date is None or r.due_date >= ref_date
    ]

    sales_bucket = _build_bucket(sales_rows)
    payments_bucket = _build_bucket(payment_rows)
    pending_total_bucket = _build_bucket(pending_rows)
    overdue_bucket = _build_bucket(overdue_rows)
    upcoming_bucket = _build_bucket(upcoming_rows)

    all_tx_ids: list[str] = []
    all_src_ids: list[str] = []
    for bucket in (sales_bucket, payments_bucket, pending_total_bucket):
        for tx_id in bucket.transaction_ids:
            if tx_id not in all_tx_ids:
                all_tx_ids.append(tx_id)
        for src_id in bucket.source_ids:
            if src_id not in all_src_ids:
                all_src_ids.append(src_id)

    resolved_producer_id = producer_rows[0].producer_id if producer_rows else target
    resolved_producer_name = next(
        (r.producer_name for r in producer_rows if r.producer_name),
        None,
    )
    doc_name = producer_rows[0].document_name if producer_rows else "financeiro.csv"

    return FinancialSummaryCalculation(
        producer_id=resolved_producer_id,
        producer_name=resolved_producer_name,
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        reference_date=ref_date.isoformat(),
        source_document=doc_name,
        sales_in_period=sales_bucket,
        registered_payments_in_period=payments_bucket,
        pending_total=pending_total_bucket,
        pending_overdue=overdue_bucket,
        pending_upcoming=upcoming_bucket,
        all_transaction_ids=all_tx_ids,
        all_source_ids=all_src_ids,
        has_any_records=bool(all_tx_ids),
    )


def build_financial_summary_tool(
    sources: Sequence[ConsultationSourceItem | Any],
) -> Callable[[str, str, str, str], dict[str, Any]]:
    """Cria a ferramenta ADK de cálculo financeiro vinculada aos registros recuperados."""

    def calcular_resumo_financeiro_produtor(
        producer: str,
        period_start: str,
        period_end: str,
        reference_date: str,
    ) -> dict[str, Any]:
        """Calcula vendas, pagamentos registrados e pendências financeiras de um produtor em financeiro.csv."""
        result = calculate_producer_financial_summary(
            producer=producer,
            period_start=period_start,
            period_end=period_end,
            reference_date=reference_date,
            sources=sources,
        )
        return result.model_dump(mode="json")

    return calcular_resumo_financeiro_produtor
