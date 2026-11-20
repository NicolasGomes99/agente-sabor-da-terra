import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from ..agents.config import to_pernambuco_date
from ..agents.consultation.financial import FINANCIAL_SOURCE_FILENAME
from ..agents.consultation.schemas import ConsultationSourceItem
from ..agents.schemas import ConversationTurn, OrchestratorFlow
from ..config import get_rag_semantic_top_k
from ..repositories.document import DocumentRepository
from ..schemas.agent_integration import (
    DocumentRetrievalContext,
    DocumentRetrievalError,
    RetrievedDocumentSources,
)
from ..services.agent_integration import document_chunks_to_source_items
from .embeddings import EmbeddingClient

_LOT_ID_RE = re.compile(r"\b(LOT-\d{4}-\d+)\b", re.IGNORECASE)
_FIN_ID_RE = re.compile(r"\b(FIN-\d{4}-\d+)\b", re.IGNORECASE)
_PRODUCER_ID_RE = re.compile(r"\b(P\d{2,4})\b", re.IGNORECASE)
_DOC_FILE_RE = re.compile(r"\b([a-z0-9_\-]+\.(?:txt|csv))\b", re.IGNORECASE)
_CERT_OR_REPORT_ID_RE = re.compile(
    r"\b((?:ORG|VS|ADAGRO)-[A-Z0-9\-]+)\b",
    re.IGNORECASE,
)

_FINANCIAL_INTENT_KEYWORDS: tuple[str, ...] = (
    "financeir",
    "resumo financeiro",
    "vendas",
    "venda",
    "pagamentos",
    "pagamento",
    "pendencia",
    "pendencias",
    "a vencer",
    "a receber",
    "vencida",
    "vencidas",
    "vencido",
    "vencidos",
    "faturamento",
    "repasse",
    "fin-2026",
    "financeiro.csv",
)

_PRICE_INTENT_KEYWORDS: tuple[str, ...] = (
    "preco",
    "precos",
    "valor",
    "valores",
    "tabela de precos",
    "desconto",
    "atacado",
)

_SEASONALITY_INTENT_KEYWORDS: tuple[str, ...] = (
    "sazonal",
    "safra",
    "entressafra",
    "epoca",
    "pedido",
    "fornecimento",
    "encomenda",
    "cotacao",
)

_FOLLOWUP_MARKERS: tuple[str, ...] = (
    "dele",
    "dela",
    "deles",
    "delas",
    "disso",
    "desse",
    "dessa",
    "desse lote",
    "dessa certificacao",
    "desse contrato",
    "desse produtor",
    "dessa produtora",
    "esse",
    "essa",
    "este",
    "esta",
    "mesmo",
    "mesma",
    "tambem",
    "e qual",
    "e quais",
    "e quanto",
    "e quando",
    "e sobre",
    "qual a validade",
    "qual o prazo",
)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_only.lower().split())


def _parse_optional_iso_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return to_pernambuco_date(value)
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return to_pernambuco_date(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_identifiers(text: str) -> dict[str, list[str]]:
    return {
        "lots": list(dict.fromkeys(m.upper() for m in _LOT_ID_RE.findall(text))),
        "financial": list(dict.fromkeys(m.upper() for m in _FIN_ID_RE.findall(text))),
        "producers": list(dict.fromkeys(m.upper() for m in _PRODUCER_ID_RE.findall(text))),
        "files": list(dict.fromkeys(m.lower() for m in _DOC_FILE_RE.findall(text))),
        "certs": list(dict.fromkeys(m.upper() for m in _CERT_OR_REPORT_ID_RE.findall(text))),
    }


def _needs_history_context(
    query_text: str,
    current_ids: Mapping[str, list[str]],
    history: Sequence[ConversationTurn],
) -> bool:
    if not history:
        return False
    has_explicit_entity = any(current_ids.values())
    normalized = _normalize_text(query_text)
    if any(marker in normalized for marker in _FOLLOWUP_MARKERS):
        return True
    return not has_explicit_entity and len(normalized.split()) <= 10


def build_contextual_query(
    query_text: str,
    history: Sequence[ConversationTurn],
    *,
    max_history_turns: int = 4,
) -> tuple[str, dict[str, list[str]]]:
    """Combina consulta atual com entidades/trechos recentes do histórico em acompanhamentos."""
    current_ids = _extract_identifiers(query_text)
    merged_ids: dict[str, list[str]] = {
        key: list(values) for key, values in current_ids.items()
    }
    if not history:
        return query_text.strip(), merged_ids

    recent_turns = list(history[-max_history_turns:])
    needs_context = _needs_history_context(query_text, current_ids, recent_turns)

    history_snippets: list[str] = []
    for turn in reversed(recent_turns):
        turn_ids = _extract_identifiers(turn.content)
        for key, values in turn_ids.items():
            # Herda identificadores do histórico apenas quando a consulta atual
            # é um acompanhamento sem novo identificador daquela categoria.
            if not current_ids[key] and needs_context:
                for val in values:
                    if val not in merged_ids[key]:
                        merged_ids[key].append(val)
        if needs_context and len(history_snippets) < 2:
            snippet = " ".join(turn.content.split())[:280]
            if snippet:
                history_snippets.append(snippet)

    if not needs_context or not history_snippets:
        return query_text.strip(), merged_ids

    context_tail = " | ".join(reversed(history_snippets))
    enriched_query = f"{query_text.strip()}\nContexto recente da conversa: {context_tail}"
    return enriched_query, merged_ids


def _matches_producer(fields: Mapping[str, str], producer_filter: str) -> bool:
    normalized_filter = _normalize_text(producer_filter)
    if not normalized_filter:
        return True
    prod_id = _normalize_text(fields.get("produtor_id", ""))
    prod_name = _normalize_text(fields.get("produtor_nome", ""))
    if prod_id == normalized_filter:
        return True
    return normalized_filter in prod_name


def _matches_field_filters(
    fields: Mapping[str, str] | None,
    field_filters: Mapping[str, str],
) -> bool:
    if not field_filters:
        return True
    if not fields:
        return False
    normalized_fields = {_normalize_text(k): v for k, v in fields.items()}
    for raw_key, raw_expected in field_filters.items():
        key = _normalize_text(raw_key)
        expected = _normalize_text(raw_expected)
        actual_raw = normalized_fields.get(key)
        if actual_raw is None:
            return False
        actual = _normalize_text(actual_raw)
        if key in {"id", "produtor_id", "lote_id", "id_transacao", "status", "status_pagamento"}:
            if actual != expected:
                return False
        elif expected not in actual:
            return False
    return True


def _has_financial_intent(
    query_text: str,
    context: DocumentRetrievalContext,
    merged_ids: Mapping[str, list[str]],
) -> bool:
    if (
        context.producer_id
        or context.period_start is not None
        or context.period_end is not None
        or context.financial_reference_date is not None
        or merged_ids.get("financial")
    ):
        return True
    normalized = _normalize_text(query_text)
    if any(
        non_fin in normalized
        for non_fin in ("preco", "precos", "tabela de precos", "forma de pagamento", "condicoes de pagamento")
    ) and "financeir" not in normalized:
        return False
    return any(keyword in normalized for keyword in _FINANCIAL_INTENT_KEYWORDS)


class RagRetrievalService:
    """Recuperação semântica (pgvector) e estruturada (exaustiva) compatível com a #50."""

    def __init__(
        self,
        repository: DocumentRepository,
        embedding_client: EmbeddingClient,
        *,
        semantic_top_k: int | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self.semantic_top_k = (
            semantic_top_k if semantic_top_k is not None else get_rag_semantic_top_k()
        )
        if self.semantic_top_k < 1:
            raise ValueError("semantic_top_k must be at least 1.")

    async def semantic_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_ids: Sequence[UUID] | None = None,
        document_names: Sequence[str] | None = None,
    ) -> list[ConsultationSourceItem]:
        cleaned = query.strip()
        if not cleaned:
            return []
        limit = top_k if top_k is not None else self.semantic_top_k
        try:
            query_embedding = await self.embedding_client.embed_query(cleaned)
            chunks = await self.repository.semantic_search_chunks(
                query_embedding,
                top_k=limit,
                document_ids=document_ids,
                document_names=document_names,
            )
            return document_chunks_to_source_items(chunks)
        except DocumentRetrievalError:
            raise
        except Exception as error:
            raise DocumentRetrievalError(
                f"Falha ao executar busca semântica documental: {error}"
            ) from error

    async def get_by_record_ids(
        self,
        record_ids: Sequence[str],
        *,
        document_name: str | None = None,
    ) -> list[ConsultationSourceItem]:
        cleaned_ids = [rid.strip() for rid in record_ids if rid and rid.strip()]
        if not cleaned_ids:
            return []
        try:
            chunks = await self.repository.list_indexed_chunks(
                document_name=document_name,
                record_ids=cleaned_ids,
            )
            return document_chunks_to_source_items(chunks)
        except Exception as error:
            raise DocumentRetrievalError(
                f"Falha ao recuperar registros por identificador: {error}"
            ) from error

    async def query_structured_records(
        self,
        *,
        document_name: str | None = None,
        document_ids: Sequence[UUID] | None = None,
        record_ids: Sequence[str] | None = None,
        field_filters: Mapping[str, str] | None = None,
    ) -> list[ConsultationSourceItem]:
        """Recuperação estruturada exaustiva (sem limite de top-k da busca semântica)."""
        try:
            chunks = await self.repository.list_indexed_chunks(
                document_name=document_name,
                document_ids=document_ids,
                record_ids=record_ids,
                only_records=True,
            )
            if field_filters:
                chunks = [
                    chunk
                    for chunk in chunks
                    if _matches_field_filters(chunk.record_fields, field_filters)
                ]
            return document_chunks_to_source_items(chunks)
        except Exception as error:
            raise DocumentRetrievalError(
                f"Falha ao executar consulta estruturada documental: {error}"
            ) from error

    async def query_financial_records(
        self,
        *,
        producer_id: str | None = None,
        date_field: Literal["data", "data_pagamento", "data_vencimento"] | None = None,
        period_start: date | datetime | str | None = None,
        period_end: date | datetime | str | None = None,
        reference_date: date | datetime | str | None = None,
        include_pending_as_of_reference: bool = False,
    ) -> list[ConsultationSourceItem]:
        """Recuperação exaustiva de registros de financeiro.csv para a ferramenta da #40."""
        start = _parse_optional_iso_date(period_start)
        end = _parse_optional_iso_date(period_end)
        ref_date = _parse_optional_iso_date(reference_date)

        try:
            chunks = await self.repository.list_indexed_chunks(
                document_name=FINANCIAL_SOURCE_FILENAME,
                only_records=True,
            )
        except Exception as error:
            raise DocumentRetrievalError(
                f"Falha ao recuperar registros financeiros: {error}"
            ) from error

        selected = []
        for chunk in chunks:
            fields = chunk.record_fields or {}
            if producer_id and not _matches_producer(fields, producer_id):
                continue

            if date_field is not None:
                field_date = _parse_optional_iso_date(fields.get(date_field))
                if field_date is None:
                    continue
                if start is not None and field_date < start:
                    continue
                if end is not None and field_date > end:
                    continue
                selected.append(chunk)
                continue

            if include_pending_as_of_reference and ref_date is not None:
                sale_date = _parse_optional_iso_date(fields.get("data"))
                pay_date = _parse_optional_iso_date(fields.get("data_pagamento"))

                in_sales_period = (
                    sale_date is not None
                    and (start is None or sale_date >= start)
                    and (end is None or sale_date <= end)
                )
                in_payment_period = (
                    pay_date is not None
                    and (start is None or pay_date >= start)
                    and (end is None or pay_date <= end)
                )
                is_pending_as_of_ref = (
                    sale_date is not None
                    and sale_date <= ref_date
                    and (pay_date is None or pay_date > ref_date)
                )
                if start is None and end is None:
                    if is_pending_as_of_ref:
                        selected.append(chunk)
                elif in_sales_period or in_payment_period or is_pending_as_of_ref:
                    selected.append(chunk)
                continue

            if start is not None or end is not None:
                sale_date = _parse_optional_iso_date(fields.get("data"))
                pay_date = _parse_optional_iso_date(fields.get("data_pagamento"))
                in_sales = (
                    sale_date is not None
                    and (start is None or sale_date >= start)
                    and (end is None or sale_date <= end)
                )
                in_payments = (
                    pay_date is not None
                    and (start is None or pay_date >= start)
                    and (end is None or pay_date <= end)
                )
                if not (in_sales or in_payments):
                    continue

            selected.append(chunk)

        return document_chunks_to_source_items(selected)

    async def retrieve_sources(
        self,
        context: DocumentRetrievalContext,
    ) -> RetrievedDocumentSources:
        """Implementa DocumentSourceProvider (#50) combinando contexto, busca exata e pgvector."""
        contextual_query, merged_ids = build_contextual_query(
            context.query_text,
            context.history,
        )

        exact_sources: list[ConsultationSourceItem] = []

        if merged_ids["lots"]:
            exact_sources.extend(
                await self.get_by_record_ids(
                    merged_ids["lots"],
                    document_name="lotes.csv",
                )
            )
        if merged_ids["financial"]:
            exact_sources.extend(
                await self.get_by_record_ids(
                    merged_ids["financial"],
                    document_name=FINANCIAL_SOURCE_FILENAME,
                )
            )
        producer_targets = list(merged_ids["producers"])
        if context.producer_id and context.producer_id.strip():
            ctx_prod = context.producer_id.strip().upper()
            if ctx_prod not in producer_targets:
                producer_targets.insert(0, ctx_prod)

        if producer_targets:
            exact_sources.extend(
                await self.get_by_record_ids(
                    producer_targets,
                    document_name="produtores.csv",
                )
            )
            # Quando há filtro estruturado por produtor (ex.: resumo consolidado #63),
            # fornece de forma exaustiva os registros históricos de lotes.csv desse produtor.
            if context.producer_id and context.producer_id.strip():
                exact_sources.extend(
                    await self.query_structured_records(
                        document_name="lotes.csv",
                        field_filters={"produtor_id": context.producer_id.strip()},
                    )
                )
            # Também inclui documentos nominais do produtor (certificações/laudos com _P00X.txt)
            try:
                all_docs = await self.repository.list_by_processing_status(("indexed",))
                matched_doc_ids = [
                    doc.id
                    for doc in all_docs
                    if any(
                        f"_{pid.lower()}" in doc.original_filename.lower()
                        for pid in producer_targets
                    )
                ]
                if matched_doc_ids:
                    producer_doc_chunks = await self.repository.list_indexed_chunks(
                        document_ids=matched_doc_ids
                    )
                    exact_sources.extend(
                        document_chunks_to_source_items(producer_doc_chunks)
                    )
            except Exception as error:
                raise DocumentRetrievalError(
                    f"Falha ao recuperar documentos do produtor: {error}"
                ) from error

        if merged_ids["files"]:
            try:
                file_chunks = await self.repository.list_indexed_chunks(
                    document_names=merged_ids["files"]
                )
                # Evita inundar o prompt se um CSV grande for citado apenas pelo nome
                exact_sources.extend(
                    document_chunks_to_source_items(file_chunks[: self.semantic_top_k])
                )
            except Exception as error:
                raise DocumentRetrievalError(
                    f"Falha ao recuperar documento citado pelo nome: {error}"
                ) from error

        semantic_sources = await self.semantic_search(
            contextual_query,
            top_k=self.semantic_top_k,
        )

        # Em consultas explícitas sobre preços, garante busca dedicada em tabela_precos se existir
        normalized_q = _normalize_text(contextual_query)
        if any(kw in normalized_q for kw in _PRICE_INTENT_KEYWORDS):
            price_hits = await self.semantic_search(
                contextual_query,
                top_k=min(5, self.semantic_top_k),
                document_names=("tabela_precos_outubro_2026.csv",),
            )
            semantic_sources = [*price_hits, *semantic_sources]

        # Na triagem (#62) ou em consultas sazonais, inclui exatamente os registros de
        # sazonalidade.csv correspondentes aos produtos mencionados, sem depender do top-k.
        is_triage_context = (
            context.flow == OrchestratorFlow.TRIAGE
            or context.solicitation_id is not None
        )
        if is_triage_context or any(
            kw in normalized_q for kw in _SEASONALITY_INTENT_KEYWORDS
        ):
            seasonality_text = normalized_q
            if is_triage_context and context.history:
                seasonality_text = _normalize_text(
                    " ".join(
                        [
                            context.query_text,
                            *(turn.content for turn in context.history[:2]),
                        ]
                    )
                )
            try:
                seasonality_chunks = await self.repository.list_indexed_chunks(
                    document_name="sazonalidade.csv",
                    only_records=True,
                )
            except Exception as error:
                raise DocumentRetrievalError(
                    f"Falha ao recuperar registros de sazonalidade: {error}"
                ) from error
            matched_seasonality = [
                chunk
                for chunk in seasonality_chunks
                if (
                    norm_prod := _normalize_text(
                        str((chunk.record_fields or {}).get("produto", ""))
                    )
                )
                and re.search(rf"\b{re.escape(norm_prod)}\b", seasonality_text)
            ]
            if matched_seasonality:
                exact_sources.extend(
                    document_chunks_to_source_items(matched_seasonality)
                )

        # Deduplica preservando ordem de relevância (acertos exatos primeiro, depois semânticos)
        merged_sources: list[ConsultationSourceItem] = []
        seen_ids: set[str] = set()
        for item in (*exact_sources, *semantic_sources):
            if item.source_id not in seen_ids:
                seen_ids.add(item.source_id)
                merged_sources.append(item)

        financial_records: list[ConsultationSourceItem] | None = None
        if _has_financial_intent(contextual_query, context, merged_ids):
            resolved_producer = context.producer_id or (
                merged_ids["producers"][0] if len(merged_ids["producers"]) == 1 else None
            )
            resolved_ref_date = context.financial_reference_date or context.reference_date
            if resolved_producer is not None and (
                context.period_start is not None
                or context.period_end is not None
                or resolved_ref_date is not None
            ):
                financial_records = await self.query_financial_records(
                    producer_id=resolved_producer,
                    period_start=context.period_start,
                    period_end=context.period_end,
                    reference_date=resolved_ref_date,
                    include_pending_as_of_reference=True,
                )
            elif resolved_producer is not None:
                financial_records = await self.query_financial_records(
                    producer_id=resolved_producer,
                )
            else:
                # Sem produtor resolvido no contexto, fornece a coleção exaustiva de financeiro.csv
                # para que a ferramenta da #40 resolva o produtor pelo nome/código sem truncar.
                financial_records = await self.query_financial_records()

        return RetrievedDocumentSources(
            sources=merged_sources,
            financial_records=financial_records,
        )
