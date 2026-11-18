from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.models import Product
from api.schemas.producer import ProducerResponse


@pytest.fixture
def producer_data() -> dict[str, object]:
    return {
        "id": uuid4(),
        "code": "P001",
        "name": "Ana Silva",
        "cpf": "01234567890",
        "active": True,
        "phone": "81999990000",
        "email": "ana@example.com",
        "address": "Rua das Flores, 10",
        "municipality": "Caruaru",
        "products": [
            {"id": uuid4(), "name": "Alface"},
            {"id": uuid4(), "name": "Coentro"},
        ],
    }


@pytest.mark.parametrize("active", [True, False])
def test_producer_response_serializes_to_json(
    producer_data: dict[str, object], active: bool,
) -> None:
    producer_data["active"] = active
    response = ProducerResponse.model_validate(producer_data)

    assert response.model_dump(mode="json") == {
        **producer_data,
        "id": str(producer_data["id"]),
        "products": [
            {"id": str(product.id), "name": product.name}
            for product in response.products
        ],
    }
    assert [product.model_dump() for product in response.products] == producer_data["products"]


def test_producer_response_from_attributes(producer_data: dict[str, object]) -> None:
    product_id = uuid4()
    source = SimpleNamespace(
        **{**producer_data, "products": [Product(id=product_id, name="Alface")]}
    )

    response = ProducerResponse.model_validate(source)

    assert response.id == source.id
    assert response.code == source.code
    assert response.name == source.name
    assert response.cpf == source.cpf
    assert response.active is source.active
    assert response.phone == source.phone
    assert response.email == source.email
    assert response.address == source.address
    assert response.municipality == source.municipality
    assert [product.model_dump() for product in response.products] == [
        {"id": product_id, "name": "Alface"}
    ]


def test_producer_response_allows_empty_products(producer_data: dict[str, object]) -> None:
    producer_data["products"] = []

    response = ProducerResponse.model_validate(producer_data)

    assert response.model_dump(mode="json")["products"] == []


def test_producer_response_preserves_null_contact_fields(
    producer_data: dict[str, object],
) -> None:
    fields = ("phone", "email", "address", "municipality")
    producer_data.update({field: None for field in fields})

    response = ProducerResponse.model_validate(producer_data)
    serialized = response.model_dump(mode="json")

    assert {field: serialized[field] for field in fields} == dict.fromkeys(fields)


@pytest.mark.parametrize("missing_field", [
    "id", "code", "name", "cpf", "active", "phone", "email", "address", "municipality", "products",
])
def test_producer_response_requires_fields(
    producer_data: dict[str, object], missing_field: str,
) -> None:
    del producer_data[missing_field]

    with pytest.raises(ValidationError) as error:
        ProducerResponse.model_validate(producer_data)

    assert error.value.errors()[0]["loc"] == (missing_field,)
    assert error.value.errors()[0]["type"] == "missing"
