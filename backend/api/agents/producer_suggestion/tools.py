import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from ..consultation.schemas.input import ConsultationSourceItem
from .schemas.input import OrderToolContract, ProducerCatalogItemContract


def _norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().strip().split())


def _whole_phrase_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return bool(
        re.search(rf"\b{re.escape(a)}\b", b)
        or re.search(rf"\b{re.escape(b)}\b", a)
    )


@runtime_checkable
class ProducerSuggestionToolProvider(Protocol):
    """Contrato das ferramentas da aplicação para sugestão de produtores (#23, #36, #28).

    Permite plugar os serviços reais da aplicação ou uma implementação simulada
    enquanto a consulta operacional de saldo por item (#28) estiver em desenvolvimento.
    """

    def get_order_with_balances(self, order_id: str) -> OrderToolContract | None:
        ...

    def list_producers_by_product(
        self,
        *,
        product_id: str | None = None,
        product_name: str | None = None,
    ) -> Sequence[ProducerCatalogItemContract]:
        ...

    def list_knowledge_sources(
        self,
        *,
        order_id: str,
        product_names: Sequence[str] | None = None,
    ) -> Sequence[ConsultationSourceItem]:
        ...


class InMemoryProducerSuggestionToolProvider:
    """Implementação simulada em memória do contrato de ferramentas para validação da #25."""

    def __init__(
        self,
        *,
        orders: Sequence[OrderToolContract | Any] = (),
        producers: Sequence[ProducerCatalogItemContract | Any] = (),
        sources: Sequence[ConsultationSourceItem] = (),
    ) -> None:
        normalized_orders = [
            o if isinstance(o, OrderToolContract) else OrderToolContract.from_order_response(o)
            for o in orders
        ]
        self._orders: dict[str, OrderToolContract] = {
            order.order_id: order for order in normalized_orders
        }
        self._producers: list[ProducerCatalogItemContract] = [
            p
            if isinstance(p, ProducerCatalogItemContract)
            else ProducerCatalogItemContract.from_producer_response(p)
            for p in producers
        ]
        self._sources: list[ConsultationSourceItem] = list(sources)

    def get_order_with_balances(self, order_id: str) -> OrderToolContract | None:
        return self._orders.get(order_id.strip())

    def list_producers_by_product(
        self,
        *,
        product_id: str | None = None,
        product_name: str | None = None,
    ) -> list[ProducerCatalogItemContract]:
        if not product_id and not product_name:
            return list(self._producers)

        target_id = product_id.strip() if product_id else None
        target_name = _norm(product_name) if product_name else None

        matched: list[ProducerCatalogItemContract] = []
        for producer in self._producers:
            for prod in producer.products:
                id_hit = bool(target_id and prod.product_id == target_id)
                name_hit = bool(
                    target_name and _whole_phrase_match(target_name, _norm(prod.product_name))
                )
                if id_hit or name_hit:
                    matched.append(producer)
                    break
        return matched

    def list_knowledge_sources(
        self,
        *,
        order_id: str,
        product_names: Sequence[str] | None = None,
    ) -> list[ConsultationSourceItem]:
        _ = (order_id, product_names)
        return list(self._sources)


def build_producer_suggestion_tools(
    tool_provider: ProducerSuggestionToolProvider | None = None,
    *,
    fallback_sources: Sequence[ConsultationSourceItem] = (),
) -> list[Callable[..., Any]]:
    """Constrói as ferramentas ADK de consulta de pedido/saldos, produtores e fontes."""

    def consultar_pedido_e_saldos(order_id: str) -> dict[str, Any]:
        """Consulta o pedido cadastrado, seus itens, condições, prazo e saldo operacional a alocar."""
        if tool_provider is None:
            return {"error": "Provedor de pedidos e saldos não configurado."}
        order = tool_provider.get_order_with_balances(order_id)
        if order is None:
            return {"error": f"Pedido '{order_id}' não encontrado."}
        return order.model_dump(mode="json")

    def consultar_produtores_por_produto(
        product_id: str = "",
        product_name: str = "",
    ) -> list[dict[str, Any]]:
        """Consulta produtores associados a um produto do catálogo, incluindo status ativo/inativo."""
        if tool_provider is None:
            return []
        producers = tool_provider.list_producers_by_product(
            product_id=product_id.strip() or None,
            product_name=product_name.strip() or None,
        )
        return [p.model_dump(mode="json") for p in producers]

    def consultar_fontes_pedido(order_id: str) -> list[dict[str, Any]]:
        """Consulta as fontes documentais recuperadas (certificações, contratos, sazonalidade, lotes)."""
        collected: list[ConsultationSourceItem] = []
        seen_ids: set[str] = set()
        if tool_provider is not None:
            for src in tool_provider.list_knowledge_sources(order_id=order_id):
                if src.source_id not in seen_ids:
                    seen_ids.add(src.source_id)
                    collected.append(src)
        for src in fallback_sources:
            if src.source_id not in seen_ids:
                seen_ids.add(src.source_id)
                collected.append(src)
        return [
            {
                "source_id": s.source_id,
                "source_kind": s.source_kind.value,
                "document_id": s.document_id,
                "document_name": s.document_name,
                "reference_label": s.reference_label,
                "record_id": s.record_id,
                "record_fields": s.record_fields,
                "content": s.content,
            }
            for s in collected
        ]

    return [
        consultar_pedido_e_saldos,
        consultar_produtores_por_produto,
        consultar_fontes_pedido,
    ]
