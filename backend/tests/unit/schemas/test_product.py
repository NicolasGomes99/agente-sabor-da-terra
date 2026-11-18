from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.models import Product
from api.schemas.product import ProductResponse


def test_product_response_from_model() -> None:
    product_id = uuid4()
    product = Product(id=product_id, name="Alface")

    response = ProductResponse.model_validate(product)

    assert response.id == product_id
    assert response.name == "Alface"


def test_product_response_serializes_to_json() -> None:
    product_id = uuid4()
    response = ProductResponse(id=product_id, name="Alface")

    assert response.model_dump(mode="json") == {
        "id": str(product_id),
        "name": "Alface",
    }


def test_product_response_rejects_invalid_uuid() -> None:
    with pytest.raises(ValidationError) as error:
        ProductResponse.model_validate({"id": "invalid-uuid", "name": "Alface"})

    assert error.value.errors()[0]["loc"] == ("id",)
    assert error.value.errors()[0]["type"] == "uuid_parsing"


@pytest.mark.parametrize("missing_field", ["id", "name"])
def test_product_response_requires_fields(missing_field: str) -> None:
    data = {"id": uuid4(), "name": "Alface"}
    del data[missing_field]

    with pytest.raises(ValidationError) as error:
        ProductResponse.model_validate(data)

    assert error.value.errors()[0]["loc"] == (missing_field,)
    assert error.value.errors()[0]["type"] == "missing"
