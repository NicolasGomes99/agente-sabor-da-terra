from datetime import date
from decimal import Decimal

import pytest

from api.agents.triage import TriageAnalysis, prepare_order_draft
from api.models.product import Product
from api.schemas.order_draft import OrderDraftConfirmation
from api.schemas.product import ProductResponse
from tests.integration.services import test_order_draft

case = test_order_draft.case
service = test_order_draft.service

pytestmark = pytest.mark.asyncio


async def test_generated_draft_can_be_reviewed_and_confirmed_with_issue_10(case):
    async with case.factory() as session:
        catalog = [
            ProductResponse.model_validate(await session.get(Product, product_id))
            for product_id in case.products
        ]
        analysis = TriageAnalysis.model_validate(
            {
                "summary": "Pedido Mercado Bom Preço.",
                "request_type": "pedido",
                "urgency": "normal",
                "urgency_reason": "Entrega em novembro.",
                "received_date_reference": "2026-10-30",
                "extracted_data": {
                    "buyer_name": "Mercado Bom Preço",
                    "delivery_date_start": "2026-11-04",
                    "delivery_date_end": "2026-11-08",
                    "delivery_time_window": "pela manhã",
                    "items": [
                        {"product": catalog[0].name, "quantity": 10, "unit": "kg"},
                        {
                            "product": catalog[1].name,
                            "quantity": 5,
                            "unit": "potes",
                            "conditional": True,
                            "condition_text": "se tiver",
                        },
                    ],
                },
            }
        )
        data = prepare_order_draft(analysis, products=catalog)
        draft = await service(session).create_draft(case.owner, data, **case.scope)
        assert draft.confirmed_order_id is None
        assert draft.data["delivery_end_date"] == "2026-11-08"
        assert draft.data["items"][1]["conditional"] is True
        confirmation = OrderDraftConfirmation.model_validate(
            {
                "buyer": data.buyer,
                "conditions": data.conditions,
                "delivery_start_date": "2026-11-06",
                "delivery_end_date": None,
                "draft_version": draft.version,
                "confirmed": True,
                "items": [
                    {
                        "draft_item_id": data.items[0].id,
                        "product_id": data.items[0].product_id,
                        "quantity": data.items[0].quantity,
                        "unit": data.items[0].unit,
                    }
                ],
            }
        )
        order, created = await service(session).confirm(
            case.owner,
            draft.id,
            confirmation,
            **case.scope,
        )
        assert created is True
        assert order.buyer == "Mercado Bom Preço"
        assert order.delivery_start_date == date(2026, 11, 6)
        assert order.delivery_end_date is None
        assert "pela manhã" in order.conditions
        assert len(order.items) == 1
        assert order.items[0].product_id == case.products[0]
        assert order.items[0].quantity == Decimal(10)
