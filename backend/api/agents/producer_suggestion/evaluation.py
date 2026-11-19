import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..consultation.schemas.input import ConsultationSourceItem, SourceKind
from .schemas.input import (
    BalanceStatus,
    OrderItemBalanceContract,
    OrderToolContract,
    ProducerCatalogItemContract,
    ProducerSuggestionInput,
    UnitEquivalence,
)
from .schemas.response import (
    CandidateProofStatus,
    CapacityComparisonStatus,
    CertificationCoverageStatus,
    ExcludedProducerInfo,
    OrderItemSuggestionResult,
    ProducerCandidateSuggestion,
    ProducerSuggestionResponse,
)

_MONTH_COLUMNS: dict[int, str] = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}

_UNIT_ALIASES: dict[str, str] = {
    "kg": "kg",
    "quilo": "kg",
    "quilos": "kg",
    "quilograma": "kg",
    "quilogramas": "kg",
    "g": "g",
    "grama": "g",
    "gramas": "g",
    "t": "tonelada",
    "ton": "tonelada",
    "tonelada": "tonelada",
    "toneladas": "tonelada",
    "un": "unidade",
    "und": "unidade",
    "unid": "unidade",
    "unidade": "unidade",
    "unidades": "unidade",
    "dz": "duzia",
    "duzia": "duzia",
    "duzias": "duzia",
    "maco": "maco",
    "macos": "maco",
    "l": "litro",
    "litro": "litro",
    "litros": "litro",
    "cx": "caixa",
    "caixa": "caixa",
    "caixas": "caixa",
}

_UNIVERSAL_UNIT_FACTORS: dict[tuple[str, str], Decimal] = {
    ("tonelada", "kg"): Decimal(1000),
    ("kg", "g"): Decimal(1000),
    ("tonelada", "g"): Decimal(1000000),
    ("duzia", "unidade"): Decimal(12),
}

_CERT_VALIDITY_RE = re.compile(
    r"(?:data\s+de\s+validade|validade(?:_certificacao)?|v[áa]lid[oa]\s+at[ée])\s*[:=]\s*"
    r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_DAP_VALIDITY_RE = re.compile(
    r"(?:dap|caf)[^.\n]{0,40}?(?:validade|v[áa]lid[oa]\s+at[ée]|vigente\s+at[ée])\s*[:=]?\s*"
    r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_CAPACITY_RE = re.compile(
    r"(?:capacidade|produ[çc][ãa]o(?:\s+estimada)?|escala(?:\s+limitada\s+a)?)\s*[:=]?\s*"
    r"(?:at[ée]\s+|cerca\s+de\s+|~)?\s*"
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(kg|quilos?|g|gramas?|toneladas?|tons?|t|unidades?|un|d[úu]zias?|dz|ma[çc]os?|litros?|l|caixas?|cx)\s*"
    r"(?:/|por\s+)(dia|semana|m[êe]s|mes|ano)",
    re.IGNORECASE,
)
_ANIMAL_ORIGIN_HINTS: tuple[str, ...] = (
    "queijo",
    "manteiga",
    "ricota",
    "nata",
    "leite",
    "iogurte",
    "mel",
    "propolis",
    "polen",
    "cera",
    "frango",
    "ovo",
    "ovos",
)


def _norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().strip().split())


def _canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    cleaned = _norm(unit).rstrip(".")
    return _UNIT_ALIASES.get(cleaned, cleaned)


def _fmt_br(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _fmt_qty(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _parse_date_token(raw: str) -> date | None:
    cleaned = raw.strip()
    try:
        if "/" in cleaned:
            d_str, m_str, y_str = cleaned.split("/")
            return date(int(y_str), int(m_str), int(d_str))
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _product_matches(target_product: str, text_or_name: str) -> bool:
    norm_target = _norm(target_product)
    norm_text = _norm(text_or_name)
    if not norm_target or not norm_text:
        return False
    if (
        norm_target == norm_text
        or re.search(rf"\b{re.escape(norm_target)}\b", norm_text)
        or re.search(rf"\b{re.escape(norm_text)}\b", norm_target)
    ):
        return True
    target_tokens = [t for t in re.findall(r"[a-z0-9]+", norm_target) if len(t) >= 3]
    text_tokens = set(re.findall(r"[a-z0-9]+", norm_text))
    if target_tokens and all(t in text_tokens for t in target_tokens):
        return True
    # Compara nome base (ex.: "goiaba paluma" -> "goiaba" em certificados que separam variedade)
    return (
        len(target_tokens) >= 2
        and target_tokens[0] in text_tokens
        and target_tokens[0] not in {"queijo", "mel", "doce", "geleia", "farinha", "acucar"}
    )


def _producer_mentioned_in_source(
    producer: ProducerCatalogItemContract,
    source: ConsultationSourceItem,
) -> bool:
    code_upper = producer.code.upper()
    combined = f"{source.document_name} {source.reference_label or ''} {source.content}"
    if re.search(rf"\b{re.escape(code_upper)}\b", combined, re.IGNORECASE):
        return True

    # Evita associar documento dedicado a outro produtor (código diferente no nome do arquivo)
    doc_codes = {
        m.upper()
        for m in re.findall(r"\bP\d{2,4}\b", source.document_name, re.IGNORECASE)
    }
    if doc_codes and code_upper not in doc_codes:
        return False

    norm_name = _norm(producer.name)
    norm_combined = _norm(combined)
    return bool(norm_name and norm_name in norm_combined)


def _parse_kv_fields(source: ConsultationSourceItem) -> dict[str, str]:
    fields: dict[str, str] = {}
    if getattr(source, "record_fields", None):
        for k, v in source.record_fields.items():  # type: ignore[union-attr]
            fields[_norm(str(k))] = str(v).strip()
        return fields
    for sep in (";", "\n", ","):
        if sep in source.content and "=" in source.content:
            for part in source.content.split(sep):
                if "=" in part:
                    k, v = part.split("=", maxsplit=1)
                    fields[_norm(k)] = v.strip()
            if fields:
                return fields
    return fields


def convert_quantity_with_known_equivalence(
    quantity: Decimal,
    from_unit: str | None,
    to_unit: str | None,
    *,
    product_name: str | None = None,
    unit_equivalences: Sequence[UnitEquivalence] = (),
) -> tuple[Decimal | None, str | None]:
    """Converte quantidade apenas quando houver equivalência conhecida (RF03, RF14, RF27)."""
    src_u = _canonical_unit(from_unit)
    dst_u = _canonical_unit(to_unit)
    if not src_u or not dst_u:
        return None, None
    if src_u == dst_u:
        return quantity, None

    if (src_u, dst_u) in _UNIVERSAL_UNIT_FACTORS:
        factor = _UNIVERSAL_UNIT_FACTORS[(src_u, dst_u)]
        return quantity * factor, f"1 {src_u} = {_fmt_qty(factor)} {dst_u}"
    if (dst_u, src_u) in _UNIVERSAL_UNIT_FACTORS:
        factor = _UNIVERSAL_UNIT_FACTORS[(dst_u, src_u)]
        return quantity / factor, f"1 {dst_u} = {_fmt_qty(factor)} {src_u}"

    norm_prod = _norm(product_name) if product_name else None
    for eq in unit_equivalences:
        if eq.product_name and norm_prod and not _product_matches(eq.product_name, norm_prod):
            continue
        eq_from = _canonical_unit(eq.from_unit)
        eq_to = _canonical_unit(eq.to_unit)
        if eq_from == src_u and eq_to == dst_u:
            return quantity * eq.factor, f"1 {eq.from_unit} = {_fmt_qty(eq.factor)} {eq.to_unit}"
        if eq_from == dst_u and eq_to == src_u:
            return quantity / eq.factor, f"1 {eq.from_unit} = {_fmt_qty(eq.factor)} {eq.to_unit}"

    return None, None


def resolve_effective_delivery_window(
    order: OrderToolContract,
    payload: ProducerSuggestionInput,
) -> tuple[date, date, bool]:
    """Usa a data exata de entrega quando informada; caso contrário, o intervalo do pedido."""
    order_start = date.fromisoformat(order.delivery_start_date)
    order_end = (
        date.fromisoformat(order.delivery_end_date)
        if order.delivery_end_date is not None
        else order_start
    )

    if payload.resolved_exact_delivery_date is not None:
        exact = payload.resolved_exact_delivery_date
        if exact < order_start or exact > order_end:
            raise ValueError(
                f"exact_delivery_date ({exact.isoformat()}) must fall within the order "
                f"delivery window ({order_start.isoformat()} to {order_end.isoformat()})."
            )
        return exact, exact, True

    if order.exact_delivery_date is not None:
        exact = date.fromisoformat(order.exact_delivery_date)
        return exact, exact, True

    return order_start, order_end, order_start == order_end


@dataclass
class _ItemRequirements:
    organic_required: bool = False
    dap_caf_required: bool = False
    sanitary_required: bool = False
    contract_source_ids: list[str] = field(default_factory=list)


def _find_contract_sources(
    order: OrderToolContract,
    sources: Sequence[ConsultationSourceItem],
) -> list[ConsultationSourceItem]:
    contracts: list[ConsultationSourceItem] = []
    norm_ref = _norm(order.contract_reference) if order.contract_reference else ""
    norm_conditions = _norm(order.conditions)
    norm_buyer = _norm(order.buyer)

    for src in sources:
        norm_doc = _norm(f"{src.document_name} {src.reference_label or ''}")
        if "contrato" not in norm_doc and "contrato" not in _norm(src.content[:200]):
            continue
        if norm_ref and (norm_ref in _norm(src.content) or norm_ref in norm_doc) or "contrato" in norm_conditions and (
            norm_buyer in _norm(src.content) or any(tok in norm_doc for tok in norm_buyer.split() if len(tok) >= 4)
        ):
            contracts.append(src)
        elif norm_ref:
            # Verifica número do contrato (ex.: 045/2026)
            num_match = re.search(r"\d+/\d{4}", norm_ref)
            if num_match and num_match.group(0) in _norm(src.content):
                contracts.append(src)
    return contracts


def _detect_item_requirements(
    order: OrderToolContract,
    item: OrderItemBalanceContract,
    contract_sources: Sequence[ConsultationSourceItem],
) -> _ItemRequirements:
    req = _ItemRequirements(
        contract_source_ids=[c.source_id for c in contract_sources]
    )
    norm_item_cond = _norm(item.item_conditions)
    norm_order_cond = _norm(order.conditions)
    norm_prod = _norm(item.product_name)

    if item.requires_organic_certification is not None:
        req.organic_required = item.requires_organic_certification
    else:
        if "organic" in norm_item_cond or (
            "organic" in norm_order_cond
            and (
                _product_matches(item.product_name, order.conditions)
                or not any(
                    other.order_item_id != item.order_item_id
                    and _product_matches(other.product_name, order.conditions)
                    for other in order.items
                )
            )
        ):
            req.organic_required = True
        if not req.organic_required:
            for contract in contract_sources:
                for line in contract.content.splitlines():
                    norm_line = _norm(line)
                    if "organic" in norm_line and _product_matches(item.product_name, norm_line):
                        req.organic_required = True
                        break

    combined_contract_text = "\n".join(
        [order.conditions, item.item_conditions, *(c.content for c in contract_sources)]
    )
    norm_combined = _norm(combined_contract_text)

    if "dap" in norm_combined or "caf" in norm_combined:
        req.dap_caf_required = True

    is_animal_product = any(hint in norm_prod for hint in _ANIMAL_ORIGIN_HINTS)
    if is_animal_product and any(
        term in norm_combined for term in ("sie", "sim", "sisbi", "laudo sanitario")
    ):
        req.sanitary_required = True

    return req


@dataclass
class _CertEvaluation:
    status: CertificationCoverageStatus
    covered_start: date | None = None
    covered_end: date | None = None
    valid_until: date | None = None
    reason: str = ""
    pending_note: str | None = None
    source_ids: list[str] = field(default_factory=list)


def _is_certificate_source(source: ConsultationSourceItem) -> bool:
    if source.source_kind == SourceKind.LOT_RECORD:
        return False
    norm_doc = _norm(source.document_name)
    norm_content = _norm(source.content[:400])
    if "lotes.csv" in norm_doc or "sazonalidade.csv" in norm_doc or "financeiro.csv" in norm_doc:
        return False
    return (
        "cert" in norm_doc
        or "certificado de conformidade" in norm_content
        or "certificacao organica" in norm_content
    )


def _certificate_covers_product(cert_content: str, product_name: str) -> bool:
    norm_content = _norm(cert_content)
    # Tenta isolar seção de produtos certificados se existir
    section_match = re.search(
        r"produtos\s+(?:certificados|que\s+eram\s+certificados)\s*:(.*?)(?:norma\s+aplicavel|dados\s+do\s+rebanho|resultado\s+da\s+auditoria|observacoes|restricoes|____|$)",
        norm_content,
        re.DOTALL,
    )
    scope_text = section_match.group(1) if section_match else norm_content
    return _product_matches(product_name, scope_text)


def _find_explicit_non_organic_source(
    producer: ProducerCatalogItemContract,
    sources: Sequence[ConsultationSourceItem],
) -> ConsultationSourceItem | None:
    """Identifica registro cadastral declarando explicitamente que o produtor não é orgânico."""
    for src in sources:
        if not _producer_mentioned_in_source(producer, src):
            continue
        fields = _parse_kv_fields(src)
        cert_flag = fields.get("certificacao_organica")
        if cert_flag and _norm(cert_flag) in {"nao", "false", "0", "nenhuma"}:
            return src
        norm_content = _norm(src.content)
        if any(
            phrase in norm_content
            for phrase in (
                "sem certificacao organica",
                "nao possui certificacao organica",
                "certificacao_organica=nao",
                "certificacao organica: nao",
            )
        ):
            return src
    return None


def _evaluate_organic_certification(
    producer: ProducerCatalogItemContract,
    product_name: str,
    window_start: date,
    window_end: date,
    sources: Sequence[ConsultationSourceItem],
) -> _CertEvaluation:
    cert_sources = [
        src
        for src in sources
        if _is_certificate_source(src) and _producer_mentioned_in_source(producer, src)
    ]
    if not cert_sources:
        non_organic_src = _find_explicit_non_organic_source(producer, sources)
        if non_organic_src is not None:
            return _CertEvaluation(
                status=CertificationCoverageStatus.PRODUCT_NOT_COVERED,
                reason=(
                    f"Registro na base ({non_organic_src.document_name}) informa "
                    f"explicitamente que {producer.name} ({producer.code}) não possui "
                    "certificação orgânica."
                ),
                source_ids=[non_organic_src.source_id],
            )
        return _CertEvaluation(
            status=CertificationCoverageStatus.UNVERIFIED,
            pending_note=(
                f"Não foi encontrado certificado orgânico de {producer.name} ({producer.code}) "
                f"nas fontes consultadas; falta comprovar certificação vigente cobrindo "
                f"{product_name} no prazo avaliado."
            ),
        )

    best_partial: _CertEvaluation | None = None
    unverified_eval: _CertEvaluation | None = None
    expired_eval: _CertEvaluation | None = None
    not_covered_eval: _CertEvaluation | None = None

    for src in cert_sources:
        covers = _certificate_covers_product(src.content, product_name)
        val_match = _CERT_VALIDITY_RE.search(src.content)
        valid_until = _parse_date_token(val_match.group(1)) if val_match else None

        if not covers:
            not_covered_eval = _CertEvaluation(
                status=CertificationCoverageStatus.PRODUCT_NOT_COVERED,
                valid_until=valid_until,
                reason=(
                    f"Certificado orgânico consultado ({src.document_name}) não cobre "
                    f"o produto '{product_name}'."
                ),
                source_ids=[src.source_id],
            )
            continue

        if valid_until is None:
            unverified_eval = _CertEvaluation(
                status=CertificationCoverageStatus.UNVERIFIED,
                pending_note=(
                    f"Certificado orgânico encontrado ({src.document_name}) sem data de "
                    f"validade identificável; falta confirmar vigência para {product_name}."
                ),
                source_ids=[src.source_id],
            )
            continue

        if valid_until >= window_end:
            return _CertEvaluation(
                status=CertificationCoverageStatus.VALID_FULL,
                covered_start=window_start,
                covered_end=window_end,
                valid_until=valid_until,
                reason=(
                    f"Certificação orgânica vigente até {_fmt_br(valid_until)} cobrindo "
                    f"'{product_name}' em todo o prazo avaliado "
                    f"({_fmt_br(window_start)}"
                    + (
                        f" a {_fmt_br(window_end)}"
                        if window_end != window_start
                        else ""
                    )
                    + ")."
                ),
                source_ids=[src.source_id],
            )

        if window_start <= valid_until < window_end:
            candidate_partial = _CertEvaluation(
                status=CertificationCoverageStatus.VALID_PARTIAL,
                covered_start=window_start,
                covered_end=valid_until,
                valid_until=valid_until,
                reason=(
                    f"Certificação orgânica cobre '{product_name}' somente em parte do "
                    f"intervalo do pedido: de {_fmt_br(window_start)} até {_fmt_br(valid_until)} "
                    f"(vencimento em {_fmt_br(valid_until)}, anterior ao fim do intervalo em "
                    f"{_fmt_br(window_end)})."
                ),
                pending_note=(
                    f"Certificação orgânica de {producer.name} ({producer.code}) cobre apenas "
                    f"as datas de {_fmt_br(window_start)} a {_fmt_br(valid_until)}. O funcionário "
                    "ainda precisa confirmar a data exata do fornecimento dentro desse período coberto."
                ),
                source_ids=[src.source_id],
            )
            if best_partial is None or (
                best_partial.valid_until is not None
                and valid_until > best_partial.valid_until
            ):
                best_partial = candidate_partial
            continue

        expired_eval = _CertEvaluation(
            status=CertificationCoverageStatus.EXPIRED,
            valid_until=valid_until,
            reason=(
                f"Certificação orgânica vencida em {_fmt_br(valid_until)}, anterior ao "
                f"prazo de entrega ({_fmt_br(window_start)})."
            ),
            source_ids=[src.source_id],
        )

    if best_partial is not None:
        return best_partial
    if unverified_eval is not None:
        return unverified_eval
    if expired_eval is not None:
        return expired_eval
    if not_covered_eval is not None:
        return not_covered_eval
    return _CertEvaluation(status=CertificationCoverageStatus.UNVERIFIED)


def _evaluate_seasonality(
    product_name: str,
    window_start: date,
    window_end: date,
    sources: Sequence[ConsultationSourceItem],
) -> tuple[str | None, list[str], bool]:
    """Extrai sazonalidade do produto nos meses do prazo (sem confundir com disponibilidade)."""
    months: list[int] = []
    cur_year, cur_month = window_start.year, window_start.month
    while (cur_year, cur_month) <= (window_end.year, window_end.month):
        months.append(cur_month)
        if cur_month == 12:
            cur_year += 1
            cur_month = 1
        else:
            cur_month += 1

    for src in sources:
        if "sazonalidade" not in _norm(src.document_name) and "sazonalidade" not in _norm(
            src.reference_label or ""
        ):
            continue
        fields = _parse_kv_fields(src)
        prod_field = fields.get("produto")
        if prod_field and _product_matches(product_name, prod_field):
            levels: list[str] = []
            all_none = True
            for m in months:
                col = _MONTH_COLUMNS[m]
                level = fields.get(col)
                if level:
                    levels.append(f"{col}: {level}")
                    if _norm(level) != "nenhuma":
                        all_none = False
                else:
                    all_none = False
            obs = fields.get("observacao")
            obs_suffix = f" ({obs})" if obs else ""
            if levels:
                summary = (
                    f"Sazonalidade documentada em {src.document_name}: "
                    f"{', '.join(levels)}{obs_suffix} — indica tendência sazonal, "
                    "não disponibilidade confirmada."
                )
                return summary, [src.source_id], all_none

    return None, [], False


def _extract_producer_capacity(
    producer: ProducerCatalogItemContract,
    product_name: str,
    sources: Sequence[ConsultationSourceItem],
) -> tuple[Decimal | None, str | None, str | None, str | None]:
    """Busca capacidade estimada documentada para o produtor/produto nas fontes."""
    for src in sources:
        if not _producer_mentioned_in_source(producer, src):
            continue
        # Tenta localizar bloco específico do produtor dentro da fonte (evitando cruzar
        # capacidades quando uma ficha técnica lista vários produtores no mesmo trecho).
        distinct_codes = {
            m.upper() for m in re.findall(r"\bP\d{2,4}\b", src.content, re.IGNORECASE)
        }
        has_multiple_producers = len(distinct_codes) > 1
        lines = src.content.splitlines()
        focused_lines: list[str] = []
        in_producer_block = not has_multiple_producers
        for idx, line in enumerate(lines):
            line_codes = {
                m.upper() for m in re.findall(r"\bP\d{2,4}\b", line, re.IGNORECASE)
            }
            if producer.code.upper() in line_codes or (
                not line_codes
                and _norm(producer.name) in _norm(line)
            ):
                in_producer_block = True
            elif in_producer_block and line_codes and producer.code.upper() not in line_codes:
                in_producer_block = False
            if in_producer_block:
                focused_lines.append(line)
                if _product_matches(product_name, line):
                    focused_lines.extend(lines[idx + 1 : idx + 4])

        if has_multiple_producers and not focused_lines:
            continue
        search_text = "\n".join(focused_lines) if focused_lines else src.content
        # Primeiro procura capacidade próxima ao nome do produto
        product_scoped_match: re.Match[str] | None = None
        for idx, line in enumerate(focused_lines):
            if _product_matches(product_name, line):
                snippet = "\n".join(focused_lines[idx : idx + 4])
                m = _CAPACITY_RE.search(snippet)
                if m:
                    product_scoped_match = m
                    break

        match = product_scoped_match or _CAPACITY_RE.search(search_text)
        if match:
            raw_val = match.group(1).replace(",", ".")
            amount = Decimal(raw_val)
            unit = _canonical_unit(match.group(2))
            period = _norm(match.group(3))
            return amount, unit, period, src.source_id
    return None, None, None, None


def _evaluate_capacity(
    producer: ProducerCatalogItemContract,
    item: OrderItemBalanceContract,
    window_start: date,
    window_end: date,
    sources: Sequence[ConsultationSourceItem],
    unit_equivalences: Sequence[UnitEquivalence],
) -> tuple[CapacityComparisonStatus, str | None, str | None, list[str]]:
    cap_amount, cap_unit, cap_period, cap_source_id = _extract_producer_capacity(
        producer,
        item.product_name,
        sources,
    )
    if cap_amount is None or cap_unit is None or cap_period is None or cap_source_id is None:
        return CapacityComparisonStatus.NOT_INFORMED, None, None, []

    cap_label = f"{_fmt_qty(cap_amount)} {cap_unit}/{cap_period}"
    if item.remaining_balance is None or not item.unit:
        return (
            CapacityComparisonStatus.INCOMPATIBLE_UNIT_OR_PERIOD,
            (
                f"Capacidade estimada documentada: {cap_label} (não comparável enquanto "
                "o saldo ou a unidade do item estiverem em aberto; estimativa não comprova estoque atual)."
            ),
            None,
            [cap_source_id],
        )

    window_days = (window_end - window_start).days + 1
    # Período compatível: capacidade semanal/diária comparada com entrega pontual ou janela <= 7 dias
    if cap_period in {"ano", "mes"}:
        return (
            CapacityComparisonStatus.INCOMPATIBLE_UNIT_OR_PERIOD,
            (
                f"Capacidade estimada documentada: {cap_label}. Não foi feita conversão "
                f"direta frente ao saldo de {_fmt_qty(item.remaining_balance)} {item.unit} "
                f"porque o período da estimativa ({cap_period}) não é diretamente compatível "
                "com a entrega pontual do pedido (estimativa não comprova estoque atual)."
            ),
            (
                f"Confirmar se a capacidade de curto prazo de {producer.name} ({producer.code}) "
                f"comporta {_fmt_qty(item.remaining_balance)} {item.unit}, pois a base informa "
                f"apenas estimativa por {cap_period} ({cap_label})."
            ),
            [cap_source_id],
        )

    comparable_cap = cap_amount * Decimal(window_days) if cap_period == "dia" else cap_amount
    converted_demand, eq_desc = convert_quantity_with_known_equivalence(
        item.remaining_balance,
        item.unit,
        cap_unit,
        product_name=item.product_name,
        unit_equivalences=unit_equivalences,
    )
    if converted_demand is None:
        return (
            CapacityComparisonStatus.INCOMPATIBLE_UNIT_OR_PERIOD,
            (
                f"Capacidade estimada documentada: {cap_label}. Não foi possível converter "
                f"o saldo de {_fmt_qty(item.remaining_balance)} {item.unit} para {cap_unit} "
                "por ausência de equivalência conhecida entre as unidades."
            ),
            (
                f"Esclarecer equivalência entre '{item.unit}' e '{cap_unit}' ou confirmar "
                f"diretamente com {producer.name} ({producer.code}) se consegue atender "
                f"{_fmt_qty(item.remaining_balance)} {item.unit}."
            ),
            [cap_source_id],
        )

    eq_note = f" (usando equivalência conhecida: {eq_desc})" if eq_desc else ""
    if converted_demand <= comparable_cap:
        return (
            CapacityComparisonStatus.COMPATIBLE,
            (
                f"Capacidade estimada documentada ({cap_label}) compatível com o saldo "
                f"de {_fmt_qty(item.remaining_balance)} {item.unit}{eq_note}; "
                "estimativa de capacidade não comprova estoque atual nem disponibilidade confirmada."
            ),
            None,
            [cap_source_id],
        )

    return (
        CapacityComparisonStatus.ABOVE_ESTIMATED_CAPACITY,
        (
            f"Saldo a alocar ({_fmt_qty(item.remaining_balance)} {item.unit}{eq_note}) "
            f"supera a capacidade estimada documentada ({cap_label}); pode exigir "
            "alocação parcial combinada com outros produtores."
        ),
        (
            f"Verificar se {producer.name} ({producer.code}) consegue atender parcialmente "
            f"ou complementar com outro produtor, pois o saldo ({_fmt_qty(item.remaining_balance)} "
            f"{item.unit}) excede a capacidade estimada ({cap_label})."
        ),
        [cap_source_id],
    )


def _evaluate_historical_supply(
    producer: ProducerCatalogItemContract,
    product_name: str,
    sources: Sequence[ConsultationSourceItem],
) -> tuple[str | None, list[str]]:
    lot_descriptions: list[str] = []
    lot_source_ids: list[str] = []

    for src in sources:
        is_lot = (
            src.source_kind == SourceKind.LOT_RECORD
            or "lotes.csv" in _norm(src.document_name)
        )
        if not is_lot:
            continue
        fields = _parse_kv_fields(src)
        prod_id = fields.get("produtor_id", "").upper()
        prod_name = fields.get("produtor_nome", "")
        lot_product = fields.get("produto", "")

        matches_producer = (
            prod_id == producer.code.upper()
            or (prod_name and _norm(producer.name) in _norm(prod_name))
            or _producer_mentioned_in_source(producer, src)
        )
        matches_product = (
            _product_matches(product_name, lot_product)
            if lot_product
            else _product_matches(product_name, src.content)
        )
        if matches_producer and matches_product:
            lot_id = fields.get("lote_id") or src.reference_label or src.source_id
            obs = fields.get("observacao", "")
            qty = fields.get("quantidade_kg", "")
            delivery = fields.get("data_entrega", "")
            qty_desc = obs if any(u in _norm(obs) for u in ("unidade", "maco", "kg", "duzia")) else (f"{qty} kg" if qty else "")
            entry = f"{lot_id} ({qty_desc}, entrega em {delivery})" if delivery else lot_id
            lot_descriptions.append(entry)
            lot_source_ids.append(src.source_id)

    if not lot_descriptions:
        return None, []

    summary = (
        f"Registros históricos de fornecimento na base (lotes.csv): "
        f"{'; '.join(lot_descriptions)} — histórico não comprova estoque atual nem "
        "disponibilidade confirmada."
    )
    return summary, lot_source_ids


def _evaluate_contractual_docs(
    producer: ProducerCatalogItemContract,
    req: _ItemRequirements,
    sources: Sequence[ConsultationSourceItem],
) -> tuple[list[str], list[str], list[str]]:
    """Verifica DAP/CAF e registro sanitário (SIE/SIM/SISBI) quando exigidos pelo contrato."""
    verified_reasons: list[str] = []
    pending: list[str] = []
    used_source_ids: list[str] = []

    producer_docs = [
        src
        for src in sources
        if src.source_kind != SourceKind.LOT_RECORD
        and "sazonalidade" not in _norm(src.document_name)
        and "financeiro" not in _norm(src.document_name)
        and _producer_mentioned_in_source(producer, src)
    ]

    if req.dap_caf_required:
        dap_doc = next(
            (src for src in producer_docs if "dap" in _norm(src.content) or "caf" in _norm(src.content)),
            None,
        )
        if dap_doc is not None:
            used_source_ids.append(dap_doc.source_id)
            used_source_ids.extend(req.contract_source_ids)
            if _DAP_VALIDITY_RE.search(dap_doc.content):
                verified_reasons.append(
                    f"DAP/CAF com vigência informada em {dap_doc.document_name}."
                )
            else:
                pending.append(
                    f"A base informa o registro de DAP/CAF de {producer.name} ({producer.code}) "
                    f"em {dap_doc.document_name}, mas falta comprovar a vigência exigida pelo contrato citado."
                )
        else:
            used_source_ids.extend(req.contract_source_ids)
            pending.append(
                f"Falta comprovar DAP ou CAF vigente de {producer.name} ({producer.code}), "
                "conforme exigência do pedido/contrato citado."
            )

    if req.sanitary_required:
        sanitary_doc = next(
            (
                src
                for src in producer_docs
                if any(tok in _norm(src.content) for tok in ("sie", "sim", "sisbi", "alvara sanitario"))
            ),
            None,
        )
        if sanitary_doc is not None:
            used_source_ids.append(sanitary_doc.source_id)
            used_source_ids.extend(req.contract_source_ids)
            verified_reasons.append(
                f"Registro sanitário (SIE/SIM/SISBI) mencionado em {sanitary_doc.document_name}."
            )
        else:
            used_source_ids.extend(req.contract_source_ids)
            pending.append(
                f"Falta comprovar registro sanitário (SIE, SIM ou SISBI) de "
                f"{producer.name} ({producer.code}) exigido para produto de origem animal."
            )

    return verified_reasons, pending, used_source_ids


def _dedupe(items: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for val in items:
        cleaned = val.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def evaluate_producer_suggestions_deterministic(
    order: OrderToolContract,
    producers_by_item: dict[str, Sequence[ProducerCatalogItemContract]],
    sources: Sequence[ConsultationSourceItem],
    payload: ProducerSuggestionInput,
) -> ProducerSuggestionResponse:
    """Avalia deterministicamente saldos, elegibilidade, certificações, capacidade e fontes (#25)."""
    window_start, window_end, exact_used = resolve_effective_delivery_window(order, payload)
    ref_iso = payload.resolved_reference_date.isoformat()
    window_label = (
        f"{_fmt_br(window_start)}"
        if window_start == window_end
        else f"{_fmt_br(window_start)} a {_fmt_br(window_end)}"
    )

    if order.cancelled:
        return ProducerSuggestionResponse(
            order_id=order.order_id,
            buyer=order.buyer,
            reference_date_used=ref_iso,
            evaluated_delivery_start=window_start.isoformat(),
            evaluated_delivery_end=window_end.isoformat(),
            exact_delivery_date_used=exact_used,
            summary=(
                f"O pedido {order.order_id} ({order.buyer}) encontra-se cancelado e não "
                "pode receber sugestões de novas alocações operacionais. A decisão sobre "
                "eventual novo pedido permanece com o funcionário."
            ),
            item_suggestions=[],
            general_pending_confirmations=[
                "Pedido cancelado: novas alocações operacionais não são permitidas."
            ],
        )

    if order.needs_item_structuring:
        return ProducerSuggestionResponse(
            order_id=order.order_id,
            buyer=order.buyer,
            reference_date_used=ref_iso,
            evaluated_delivery_start=window_start.isoformat(),
            evaluated_delivery_end=window_end.isoformat(),
            exact_delivery_date_used=exact_used,
            summary=(
                f"O pedido {order.order_id} ({order.buyer}) ainda não possui itens "
                "estruturados cadastrados para consulta de saldo e associação de produtores. "
                "Estruture os itens do pedido antes de alocar fornecedores."
            ),
            item_suggestions=[],
            general_pending_confirmations=[
                "Estruturar os itens do pedido com produto do catálogo, quantidade e unidade."
            ],
        )

    contract_sources = _find_contract_sources(order, sources)
    item_results: list[OrderItemSuggestionResult] = []
    general_pendings: list[str] = []

    for item in order.items:
        req = _detect_item_requirements(order, item, contract_sources)
        associated_producers = list(producers_by_item.get(item.order_item_id, ()))

        req_qty_float = float(item.requested_quantity) if item.requested_quantity is not None else None
        alloc_qty_float = float(item.allocated_quantity) if item.allocated_quantity is not None else None
        bal_float = float(item.remaining_balance) if item.remaining_balance is not None else None
        unit_text = item.unit or "unidade não informada"

        if item.balance_status == BalanceStatus.FULLY_ALLOCATED:
            alloc_msg = (
                f"A quantidade solicitada ({_fmt_qty(item.requested_quantity)} {unit_text}) "
                f"já está integralmente alocada em alocações operacionais vigentes "
                f"(saldo a alocar: 0 {unit_text})."
                if item.requested_quantity is not None
                else f"A quantidade solicitada já está integralmente alocada (saldo a alocar: 0 {unit_text})."
            )
            item_results.append(
                OrderItemSuggestionResult(
                    order_item_id=item.order_item_id,
                    product_id=item.product_id,
                    product_name=item.product_name,
                    requested_quantity=req_qty_float,
                    allocated_quantity=alloc_qty_float,
                    remaining_balance=0.0,
                    unit=item.unit,
                    balance_status=BalanceStatus.FULLY_ALLOCATED,
                    allocation_message=alloc_msg,
                    organic_certification_required=req.organic_required,
                )
            )
            continue

        if item.balance_status == BalanceStatus.INDETERMINED:
            pending_reason = item.balance_pending_reason or (
                "Saldo a alocar indeterminado por ausência ou divergência de dados nas alocações."
            )
            alloc_msg = (
                f"Saldo a alocar indeterminado ({pending_reason}). "
                "A quantidade a alocar permanece em aberto até esclarecimento pelo funcionário."
            )
        else:
            assert item.remaining_balance is not None
            alloc_part = (
                f" (solicitado: {_fmt_qty(item.requested_quantity)} {unit_text}; "
                f"alocações operacionais vigentes: {_fmt_qty(item.allocated_quantity or Decimal(0))} {unit_text})"
                if item.requested_quantity is not None
                else ""
            )
            alloc_msg = (
                f"Saldo a alocar informado pela aplicação: "
                f"{_fmt_qty(item.remaining_balance)} {unit_text}{alloc_part}."
            )

        seasonality_summary, seasonality_sources, is_out_of_season = _evaluate_seasonality(
            item.product_name,
            window_start,
            window_end,
            sources,
        )

        candidates: list[ProducerCandidateSuggestion] = []
        excluded: list[ExcludedProducerInfo] = []

        for producer in associated_producers:
            supplies_product = any(
                prod.product_id == item.product_id
                or _product_matches(item.product_name, prod.product_name)
                for prod in producer.products
            )

            exclusion_reasons: list[str] = []
            exclusion_sources: list[str] = []

            if not producer.active:
                exclusion_reasons.append(
                    f"Produtor {producer.name} ({producer.code}) está inativo no cadastro."
                )
            if not supplies_product:
                exclusion_reasons.append(
                    f"Produtor {producer.name} ({producer.code}) não está associado ao produto "
                    f"'{item.product_name}' no catálogo."
                )

            if exclusion_reasons:
                excluded.append(
                    ExcludedProducerInfo(
                        producer_id=producer.producer_id,
                        producer_code=producer.code,
                        producer_name=producer.name,
                        reasons=exclusion_reasons,
                        source_ids=_dedupe(exclusion_sources),
                    )
                )
                continue

            reasons: list[str] = [
                f"Produtor ativo associado a '{item.product_name}' no catálogo (possível fornecedor)."
            ]
            pending_confirmations: list[str] = []
            cand_sources: list[str] = []

            cert_status = CertificationCoverageStatus.NOT_REQUIRED
            cert_cov_start: str | None = None
            cert_cov_end: str | None = None
            needs_proof_confirmation = False

            if req.organic_required:
                cert_eval = _evaluate_organic_certification(
                    producer,
                    item.product_name,
                    window_start,
                    window_end,
                    sources,
                )
                cert_status = cert_eval.status
                cand_sources.extend(cert_eval.source_ids)
                cand_sources.extend(req.contract_source_ids)

                if cert_eval.status in {
                    CertificationCoverageStatus.EXPIRED,
                    CertificationCoverageStatus.PRODUCT_NOT_COVERED,
                }:
                    excluded.append(
                        ExcludedProducerInfo(
                            producer_id=producer.producer_id,
                            producer_code=producer.code,
                            producer_name=producer.name,
                            reasons=[cert_eval.reason],
                            source_ids=_dedupe([*cert_eval.source_ids, *req.contract_source_ids]),
                        )
                    )
                    continue

                if cert_eval.status == CertificationCoverageStatus.VALID_FULL:
                    cert_cov_start = cert_eval.covered_start.isoformat() if cert_eval.covered_start else None
                    cert_cov_end = cert_eval.covered_end.isoformat() if cert_eval.covered_end else None
                    reasons.append(cert_eval.reason)
                elif cert_eval.status == CertificationCoverageStatus.VALID_PARTIAL:
                    cert_cov_start = cert_eval.covered_start.isoformat() if cert_eval.covered_start else None
                    cert_cov_end = cert_eval.covered_end.isoformat() if cert_eval.covered_end else None
                    needs_proof_confirmation = True
                    reasons.append(cert_eval.reason)
                    if cert_eval.pending_note:
                        pending_confirmations.append(cert_eval.pending_note)
                else:
                    needs_proof_confirmation = True
                    if cert_eval.pending_note:
                        pending_confirmations.append(cert_eval.pending_note)

            contract_reasons, contract_pending, contract_src_ids = _evaluate_contractual_docs(
                producer,
                req,
                sources,
            )
            reasons.extend(contract_reasons)
            if contract_pending:
                needs_proof_confirmation = True
                pending_confirmations.extend(contract_pending)
            cand_sources.extend(contract_src_ids)

            if seasonality_summary:
                cand_sources.extend(seasonality_sources)
                if is_out_of_season:
                    needs_proof_confirmation = True
                    pending_confirmations.append(
                        f"Sazonalidade registrada como 'nenhuma' para '{item.product_name}' "
                        f"no período ({window_label}); confirmar se há produção ou estoque disponível."
                    )

            cap_status, cap_summary, cap_pending, cap_sources = _evaluate_capacity(
                producer,
                item,
                window_start,
                window_end,
                sources,
                payload.unit_equivalences,
            )
            cand_sources.extend(cap_sources)
            if cap_pending:
                pending_confirmations.append(cap_pending)

            hist_summary, hist_sources = _evaluate_historical_supply(
                producer,
                item.product_name,
                sources,
            )
            cand_sources.extend(hist_sources)

            # Sempre exige confirmação operacional de disponibilidade para quantidade e data propostas
            if item.remaining_balance is not None and item.unit:
                pending_confirmations.append(
                    f"Confirmar disponibilidade operacional com {producer.name} ({producer.code}) "
                    f"para {_fmt_qty(item.remaining_balance)} {item.unit} de '{item.product_name}' "
                    f"na data de entrega proposta ({window_label})."
                )
            else:
                pending_confirmations.append(
                    f"Esclarecer o saldo em aberto de '{item.product_name}' e confirmar "
                    f"disponibilidade operacional com {producer.name} ({producer.code}) "
                    f"para a quantidade e a data definidas ({window_label})."
                )

            proof_status = (
                CandidateProofStatus.NEEDS_CONFIRMATION
                if needs_proof_confirmation
                else CandidateProofStatus.SUFFICIENT_PROOF
            )
            candidates.append(
                ProducerCandidateSuggestion(
                    producer_id=producer.producer_id,
                    producer_code=producer.code,
                    producer_name=producer.name,
                    proof_status=proof_status,
                    certification_status=cert_status,
                    certification_covered_start=cert_cov_start,
                    certification_covered_end=cert_cov_end,
                    seasonality_summary=seasonality_summary,
                    estimated_capacity_summary=cap_summary,
                    capacity_comparison_status=cap_status,
                    historical_supply_summary=hist_summary,
                    availability_confirmed=False,
                    reasons=_dedupe(reasons),
                    pending_confirmations=_dedupe(pending_confirmations),
                    source_ids=_dedupe(cand_sources),
                )
            )

        # Ordena: primeiro candidatos com comprovação suficiente, depois os que dependem de confirmação
        candidates.sort(
            key=lambda c: (
                0 if c.proof_status == CandidateProofStatus.SUFFICIENT_PROOF else 1,
                c.producer_code,
            )
        )

        insufficient = len(candidates) == 0
        insufficient_reason: str | None = None
        staff_note: str | None = None
        if insufficient:
            if excluded:
                insufficient_reason = (
                    f"Nenhum produtor apto disponível para '{item.product_name}': "
                    "todos os produtores associados foram excluídos por incompatibilidade comprovada."
                )
            else:
                insufficient_reason = (
                    f"Não foram encontrados produtores ativos associados a '{item.product_name}' "
                    "na base consultada."
                )
            staff_note = (
                "A decisão sobre como prosseguir (buscar outro fornecedor, negociar "
                "substituição ou revisar o pedido) permanece com o funcionário."
            )

        item_results.append(
            OrderItemSuggestionResult(
                order_item_id=item.order_item_id,
                product_id=item.product_id,
                product_name=item.product_name,
                requested_quantity=req_qty_float,
                allocated_quantity=alloc_qty_float,
                remaining_balance=bal_float,
                unit=item.unit,
                balance_status=item.balance_status or BalanceStatus.INDETERMINED,
                allocation_message=alloc_msg,
                organic_certification_required=req.organic_required,
                candidates=candidates,
                excluded_producers=excluded,
                alternative_suggestions=[],
                insufficient_data=insufficient,
                insufficient_data_reason=insufficient_reason,
                staff_decision_note=staff_note,
            )
        )

    summary = compose_deterministic_suggestion_summary(
        order=order,
        window_start=window_start,
        window_end=window_end,
        exact_used=exact_used,
        reference_date=payload.resolved_reference_date,
        item_results=item_results,
    )

    return ProducerSuggestionResponse(
        order_id=order.order_id,
        buyer=order.buyer,
        reference_date_used=ref_iso,
        evaluated_delivery_start=window_start.isoformat(),
        evaluated_delivery_end=window_end.isoformat(),
        exact_delivery_date_used=exact_used,
        summary=summary,
        item_suggestions=item_results,
        general_pending_confirmations=_dedupe(general_pendings),
    )


def compose_deterministic_suggestion_summary(
    *,
    order: OrderToolContract,
    window_start: date,
    window_end: date,
    exact_used: bool,
    reference_date: date,
    item_results: Sequence[OrderItemSuggestionResult],
) -> str:
    """Compõe texto determinístico em português cobrindo saldos, candidatos, exclusões e pendências."""
    date_label = (
        f"data exata de entrega {_fmt_br(window_start)}"
        if exact_used
        else f"intervalo de entrega {_fmt_br(window_start)} a {_fmt_br(window_end)}"
    )
    lines = [
        (
            f"Sugestão de produtores para o pedido {order.order_id} ({order.buyer}) — "
            f"{date_label} (referência: {_fmt_br(reference_date)}):"
        )
    ]

    for item in item_results:
        lines.append(f"\nItem '{item.product_name}' ({item.order_item_id}): {item.allocation_message}")
        if item.balance_status == BalanceStatus.FULLY_ALLOCATED:
            continue

        sufficient = [
            c for c in item.candidates if c.proof_status == CandidateProofStatus.SUFFICIENT_PROOF
        ]
        pending_proof = [
            c for c in item.candidates if c.proof_status == CandidateProofStatus.NEEDS_CONFIRMATION
        ]

        if sufficient:
            lines.append("  Candidatos com comprovação suficiente:")
            for cand in sufficient:
                lines.append(
                    f"  - {cand.producer_name} ({cand.producer_code}): "
                    + " ".join(cand.reasons)
                )
                if cand.seasonality_summary:
                    lines.append(f"    * Sazonalidade: {cand.seasonality_summary}")
                if cand.estimated_capacity_summary:
                    lines.append(f"    * Capacidade estimada: {cand.estimated_capacity_summary}")
                if cand.historical_supply_summary:
                    lines.append(f"    * Histórico de fornecimento: {cand.historical_supply_summary}")
                lines.append(
                    "    * Disponibilidade confirmada: Não (pendente de confirmação operacional)."
                )
                if cand.pending_confirmations:
                    lines.append(
                        "    * O que confirmar: " + " | ".join(cand.pending_confirmations)
                    )

        if pending_proof:
            lines.append("  Candidatos que ainda dependem de confirmação:")
            for cand in pending_proof:
                lines.append(
                    f"  - {cand.producer_name} ({cand.producer_code}): "
                    + " ".join(cand.reasons)
                )
                if cand.seasonality_summary:
                    lines.append(f"    * Sazonalidade: {cand.seasonality_summary}")
                if cand.estimated_capacity_summary:
                    lines.append(f"    * Capacidade estimada: {cand.estimated_capacity_summary}")
                if cand.historical_supply_summary:
                    lines.append(f"    * Histórico de fornecimento: {cand.historical_supply_summary}")
                lines.append(
                    "    * Disponibilidade confirmada: Não (pendente de confirmação operacional)."
                )
                if cand.pending_confirmations:
                    lines.append(
                        "    * O que confirmar: " + " | ".join(cand.pending_confirmations)
                    )

        if item.excluded_producers:
            lines.append("  Produtores excluídos por incompatibilidade:")
            for excl in item.excluded_producers:
                lines.append(
                    f"  - {excl.producer_name} ({excl.producer_code}): "
                    + " ".join(excl.reasons)
                )

        if item.insufficient_data and item.insufficient_data_reason:
            lines.append(f"  Pendência: {item.insufficient_data_reason}")
            if item.staff_decision_note:
                lines.append(f"  {item.staff_decision_note}")

        if item.alternative_suggestions:
            lines.append("  Alternativas sugeridas (decisão do funcionário):")
            for alt in item.alternative_suggestions:
                lines.append(
                    f"  - Substituiria '{alt.replaces_product_name}' ({alt.replaces_order_item_id}) "
                    f"por '{alt.alternative_product_name}': {alt.reason} "
                    f"({alt.candidate_producers_summary}). Decisão de aceitação com o funcionário."
                )

    return "\n".join(lines)
