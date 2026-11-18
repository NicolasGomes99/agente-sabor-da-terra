from uuid import uuid4

import pytest
from api.schemas.order import OrderCreate, OrderResponse, OrderUpdate
from pydantic import ValidationError


def valid_payload() -> dict:
    return {
        "buyer": "Mercado Central",
        "conditions": "Entrega pela manhã",
        "delivery_start_date": "2026-12-05",
        "delivery_end_date": None,
        "items": [
            {
                "product_id": str(uuid4()),
                "quantity": "10.125",
                "unit": "kg",
            }
        ],
    }


def test_create_accepts_single_date_and_trims_text() -> None:
    payload = valid_payload()
    payload["buyer"] = "  Mercado Central  "
    payload["items"][0]["unit"] = " kg "
    order = OrderCreate.model_validate(payload)
    assert order.buyer == "Mercado Central"
    assert order.items[0].unit == "kg"
    assert str(order.items[0].quantity) == "10.125"
    assert order.delivery_end_date is None


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "1.2345", "abc"])
def test_create_rejects_invalid_quantity(quantity: str) -> None:
    payload = valid_payload()
    payload["items"][0]["quantity"] = quantity
    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)


@pytest.mark.parametrize("unit", ["", "   ", "\t\n"])
def test_create_rejects_blank_unit(unit: str) -> None:
    payload = valid_payload()
    payload["items"][0]["unit"] = unit
    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)


@pytest.mark.parametrize("schema", [OrderCreate, OrderUpdate])
def test_write_requires_items(schema) -> None:
    payload = valid_payload()
    payload["items"] = []
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize("schema", [OrderCreate, OrderUpdate])
def test_write_rejects_inverted_dates(schema) -> None:
    payload = valid_payload()
    payload["delivery_end_date"] = "2026-12-04"
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_create_accepts_interval() -> None:
    payload = valid_payload()
    payload["delivery_end_date"] = "2026-12-07"
    order = OrderCreate.model_validate(payload)
    assert order.delivery_end_date.isoformat() == "2026-12-07"


def test_create_rejects_client_assigned_item_id() -> None:
    payload = valid_payload()
    payload["items"][0]["id"] = str(uuid4())
    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)


def test_update_accepts_existing_and_new_items() -> None:
    payload = valid_payload()
    item_id = uuid4()
    payload["items"][0]["id"] = str(item_id)
    payload["items"].append(
        {
            "product_id": str(uuid4()),
            "quantity": "2",
            "unit": "unidades",
        }
    )
    order = OrderUpdate.model_validate(payload)
    assert order.items[0].id == item_id
    assert order.items[1].id is None


def test_update_rejects_duplicate_item_ids() -> None:
    payload = valid_payload()
    payload["items"][0]["id"] = str(uuid4())
    payload["items"].append(dict(payload["items"][0]))
    with pytest.raises(ValidationError):
        OrderUpdate.model_validate(payload)


def test_response_preserves_legacy_description_and_marks_pending_items() -> None:
    response = OrderResponse.model_validate(
        {
            "id": str(uuid4()),
            "session_id": None,
            "buyer": "Pedido antigo",
            "conditions": "",
            "delivery_start_date": "2026-12-05",
            "delivery_end_date": None,
            "cancelled": False,
            "products": "  Tomate: 10 kg; Alface: 5 unidades\n",
            "items": [],
        }
    )
    serialized = response.model_dump(mode="json")
    assert serialized["needs_item_structuring"] is True
    assert serialized["products"] == "  Tomate: 10 kg; Alface: 5 unidades\n"


def test_response_includes_item_id_and_product() -> None:
    payload = valid_payload()
    product_id = payload["items"][0]["product_id"]
    item_id = str(uuid4())
    payload["items"][0].update(
        {
            "id": item_id,
            "product": {"id": product_id, "name": "Tomate"},
        }
    )
    response = OrderResponse.model_validate(
        {
            **payload,
            "id": str(uuid4()),
            "session_id": None,
            "cancelled": False,
            "products": "",
        }
    ).model_dump(mode="json")
    assert response["needs_item_structuring"] is False
    assert response["items"][0]["id"] == item_id
    assert response["items"][0]["product"]["name"] == "Tomate"
