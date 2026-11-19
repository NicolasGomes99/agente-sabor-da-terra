from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field


def format_brl_currency(value: Decimal | float | str) -> str:
    """Formata um valor numérico no padrão monetário brasileiro (ex.: R$ 1.020,00)."""
    dec = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if dec < 0 else ""
    abs_dec = abs(dec)
    integer_part = int(abs_dec)
    cents_part = int((abs_dec - Decimal(integer_part)) * 100)
    int_formatted = f"{integer_part:,}".replace(",", ".")
    return f"{sign}R$ {int_formatted},{cents_part:02d}"


class FinancialCalculationBucket(BaseModel):
    total_amount: Decimal = Field(
        default=Decimal("0.00"),
        description="Valor total calculado para este grupo de transações.",
    )
    formatted_total: str = Field(
        default="R$ 0,00",
        description="Valor total formatado em reais (R$).",
    )
    transaction_ids: list[str] = Field(
        default_factory=list,
        description="Lista ordenada de id_transacao usados neste cálculo.",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Lista ordenada de source_id (DocumentChunk) correspondentes.",
    )
    due_dates: list[str] = Field(
        default_factory=list,
        description="Datas de vencimento (AAAA-MM-DD) das transações deste grupo.",
    )
    payment_dates: list[str] = Field(
        default_factory=list,
        description="Datas de pagamento (AAAA-MM-DD) das transações deste grupo.",
    )
    source_document: str = Field(
        default="financeiro.csv",
        description="Nome do arquivo CSV original de onde vieram os registros.",
    )
    has_records: bool = Field(
        default=False,
        description="True quando ao menos uma transação elegível foi encontrada para este cálculo.",
    )


class ProducerMatchCandidate(BaseModel):
    producer_id: str = Field(
        min_length=1,
        description="Código identificador do produtor na base financeira (ex.: P001).",
    )
    producer_name: str | None = Field(
        default=None,
        description="Nome completo do produtor registrado na base financeira.",
    )


class FinancialSummaryCalculation(BaseModel):
    producer_id: str = Field(
        min_length=1,
        description="Identificador do produtor consultado (ex.: P004).",
    )
    producer_name: str | None = Field(
        default=None,
        description="Nome do produtor encontrado nos registros, quando disponível.",
    )
    period_start: str = Field(
        description="Data inicial do período consultado (AAAA-MM-DD).",
    )
    period_end: str = Field(
        description="Data final do período consultado (AAAA-MM-DD).",
    )
    reference_date: str = Field(
        description="Data de referência usada para avaliar pagamentos e pendências (AAAA-MM-DD).",
    )
    source_document: str = Field(
        default="financeiro.csv",
        description="Referência ao documento CSV original.",
    )
    sales_in_period: FinancialCalculationBucket = Field(
        default_factory=FinancialCalculationBucket,
        description="Vendas selecionadas pela data da transação dentro do período.",
    )
    registered_payments_in_period: FinancialCalculationBucket = Field(
        default_factory=FinancialCalculationBucket,
        description="Pagamentos registrados selecionados pela data de pagamento dentro do período.",
    )
    pending_total: FinancialCalculationBucket = Field(
        default_factory=FinancialCalculationBucket,
        description="Total de pendências financeiras na data de referência (incluindo períodos anteriores).",
    )
    pending_overdue: FinancialCalculationBucket = Field(
        default_factory=FinancialCalculationBucket,
        description="Pendências vencidas antes da data de referência.",
    )
    pending_upcoming: FinancialCalculationBucket = Field(
        default_factory=FinancialCalculationBucket,
        description="Pendências a vencer na data de referência ou depois.",
    )
    all_transaction_ids: list[str] = Field(
        default_factory=list,
        description="União ordenada de todos os id_transacao utilizados nos cálculos.",
    )
    all_source_ids: list[str] = Field(
        default_factory=list,
        description="União ordenada de todos os source_id utilizados nos cálculos.",
    )
    has_any_records: bool = Field(
        default=False,
        description="True quando ao menos um registro financeiro foi utilizado em algum cálculo.",
    )
    is_ambiguous_producer: bool = Field(
        default=False,
        description="True quando o critério informado corresponde a mais de um produtor em financeiro.csv.",
    )
    matching_producers: list[ProducerMatchCandidate] = Field(
        default_factory=list,
        description="Lista de produtores correspondentes quando há ambiguidade na busca.",
    )
    clarification_message: str | None = Field(
        default=None,
        description="Mensagem de esclarecimento solicitando especificação do produtor em caso de ambiguidade.",
    )
    is_exhaustive_source: bool = Field(
        default=True,
        description="True quando o cálculo utilizou a coleção exaustiva de registros de financeiro.csv.",
    )
