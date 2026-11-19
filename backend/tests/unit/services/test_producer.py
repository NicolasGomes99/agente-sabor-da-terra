from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from api.models import Producer, Product
from api.repositories.producer import ProducerRepository
from api.services.producer import ProducerNotFoundError, ProducerService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def repository() -> AsyncMock:
    return AsyncMock(spec=ProducerRepository)


@pytest.fixture
def producer_data() -> dict[str, object]:
    return {
        "id": uuid4(), "code": "P001", "name": "Ana Silva", "cpf": "01234567890",
        "active": True, "phone": "81999990000", "email": "ana@example.com",
        "address": "Rua das Flores, 10", "municipality": "Caruaru",
    }


async def test_list_producers_builds_responses_with_associated_products(
    repository: AsyncMock, producer_data: dict[str, object],
) -> None:
    other_data = {
        "id": uuid4(), "code": "P002", "name": "Bruno Silva", "cpf": "12345678901",
        "active": False, "phone": None, "email": None, "address": None, "municipality": None,
    }
    first, second = Producer(**other_data), Producer(**producer_data)
    alface_id, coentro_id = uuid4(), uuid4()
    repository.list_all.return_value = [first, second]
    repository.list_products_by_producer_ids.return_value = {
        second.id: [Product(id=coentro_id, name="Coentro")],
        first.id: [Product(id=alface_id, name="Alface")],
    }

    result = await ProducerService(repository).list_producers()

    assert [response.model_dump() for response in result] == [
        {**other_data, "products": [{"id": alface_id, "name": "Alface"}]},
        {**producer_data, "products": [{"id": coentro_id, "name": "Coentro"}]},
    ]
    repository.list_all.assert_awaited_once_with(product_id=None)


async def test_list_producers_loads_products_in_batch(
    repository: AsyncMock, producer_data: dict[str, object],
) -> None:
    first = Producer(**producer_data)
    second = Producer(**{
        **producer_data, "id": uuid4(), "code": "P002", "cpf": "12345678901",
    })
    repository.list_all.return_value = [first, second]
    repository.list_products_by_producer_ids.return_value = {first.id: [], second.id: []}

    result = await ProducerService(repository).list_producers()

    assert [response.id for response in result] == [first.id, second.id]
    repository.list_products_by_producer_ids.assert_awaited_once_with([first.id, second.id])


async def test_list_producers_forwards_product_filter(
    repository: AsyncMock, producer_data: dict[str, object],
) -> None:
    producer = Producer(**producer_data)
    alface_id, coentro_id = uuid4(), uuid4()
    repository.list_all.return_value = [producer]
    repository.list_products_by_producer_ids.return_value = {
        producer.id: [
            Product(id=alface_id, name="Alface"), Product(id=coentro_id, name="Coentro"),
        ],
    }

    result = await ProducerService(repository).list_producers(product_id=alface_id)

    repository.list_all.assert_awaited_once_with(product_id=alface_id)
    assert [response.model_dump() for response in result] == [{
        **producer_data,
        "products": [{"id": alface_id, "name": "Alface"}, {"id": coentro_id, "name": "Coentro"}],
    }]


@pytest.mark.parametrize("product_id", [None, uuid4()])
async def test_list_producers_returns_empty_list(
    repository: AsyncMock, product_id: UUID | None,
) -> None:
    repository.list_all.return_value = []

    assert await ProducerService(repository).list_producers(product_id=product_id) == []
    repository.list_all.assert_awaited_once_with(product_id=product_id)
    repository.list_products_by_producer_ids.assert_not_awaited()


async def test_list_producers_includes_producers_without_products(
    repository: AsyncMock, producer_data: dict[str, object],
) -> None:
    producer = Producer(**producer_data)
    repository.list_all.return_value = [producer]
    repository.list_products_by_producer_ids.return_value = {producer.id: []}

    result = await ProducerService(repository).list_producers()

    assert [response.model_dump() for response in result] == [{**producer_data, "products": []}]


@pytest.mark.parametrize("active", [True, False])
async def test_get_producer_builds_response_with_associated_products(
    repository: AsyncMock, producer_data: dict[str, object], active: bool,
) -> None:
    producer_data["active"] = active
    producer = Producer(**producer_data)
    alface_id, coentro_id = uuid4(), uuid4()
    repository.get_by_id.return_value = producer
    repository.list_products_by_producer_ids.return_value = {
        producer.id: [
            Product(id=alface_id, name="Alface"), Product(id=coentro_id, name="Coentro"),
        ],
    }

    result = await ProducerService(repository).get_producer(producer.id)

    assert result.model_dump() == {
        **producer_data,
        "products": [{"id": alface_id, "name": "Alface"}, {"id": coentro_id, "name": "Coentro"}],
    }
    repository.get_by_id.assert_awaited_once_with(producer.id)
    repository.list_products_by_producer_ids.assert_awaited_once_with([producer.id])


async def test_get_producer_without_products_returns_empty_products(
    repository: AsyncMock, producer_data: dict[str, object],
) -> None:
    producer = Producer(**producer_data)
    repository.get_by_id.return_value = producer
    repository.list_products_by_producer_ids.return_value = {producer.id: []}

    result = await ProducerService(repository).get_producer(producer.id)

    assert result.model_dump() == {**producer_data, "products": []}


async def test_get_producer_raises_for_unknown_id(repository: AsyncMock) -> None:
    producer_id = uuid4()
    repository.get_by_id.return_value = None

    with pytest.raises(ProducerNotFoundError) as error:
        await ProducerService(repository).get_producer(producer_id)

    assert error.value.args == (producer_id,)
    repository.get_by_id.assert_awaited_once_with(producer_id)
    repository.list_products_by_producer_ids.assert_not_awaited()
