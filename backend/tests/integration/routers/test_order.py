from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api import database
from api.app import app
from api.models.order import Order
from api.models.product import Product
from api.models.user import User
from api.services.auth import AuthService

pytestmark = pytest.mark.asyncio

PASSWORD = "order-http-test-password"
TEST_SECRET = "order-http-tests-only-secret-key-at-least-32-bytes"


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    @asynccontextmanager
    async def test_session_scope() -> AsyncIterator[AsyncSession]:
        # Both authentication and the API use the existing isolated test session.
        # The outer db_session fixture owns its lifetime and rollback.
        yield db_session

    monkeypatch.setattr(database, "get_session_maker", lambda: test_session_scope)
    db_session.add(
        User(
            id=uuid4(),
            email="orders-http@example.com",
            password_hash=AuthService.hash_password(PASSWORD),
        )
    )
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "email": "orders-http@example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def product_ids(db_session: AsyncSession) -> tuple[str, str]:
    first, second = uuid4(), uuid4()
    db_session.add_all(
        [
            Product(id=first, name=f"Tomate HTTP {first}"),
            Product(id=second, name=f"Alface HTTP {second}"),
        ]
    )
    await db_session.commit()
    return str(first), str(second)


def payload(product_ids: tuple[str, str]) -> dict:
    return {
        "buyer": "Mercado HTTP",
        "conditions": "Entregar pela manhã",
        "delivery_start_date": "2026-12-05",
        "delivery_end_date": None,
        "items": [
            {"product_id": product_ids[0], "quantity": "10.125", "unit": "kg"},
            {"product_id": product_ids[1], "quantity": "5", "unit": "unidades"},
        ],
    }


async def create(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    data: dict,
) -> dict:
    response = await client.post("/orders", headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def read(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    order_id: str,
) -> dict:
    response = await client.get(f"/orders/{order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_list_and_read_two_structured_items(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
) -> None:
    created = await create(client, headers, payload(product_ids))
    order_id = created["id"]
    saved = await read(client, headers, order_id)
    assert saved["buyer"] == "Mercado HTTP"
    assert saved["conditions"] == "Entregar pela manhã"
    assert saved["delivery_end_date"] is None
    assert saved["needs_item_structuring"] is False
    assert len(saved["items"]) == 2
    assert len({item["id"] for item in saved["items"]}) == 2
    assert {item["product_id"] for item in saved["items"]} == set(product_ids)
    assert all(item["product"]["name"] for item in saved["items"])
    response = await client.get("/orders", headers=headers)
    assert response.status_code == 200, response.text
    assert any(order["id"] == order_id for order in response.json())


async def test_update_preserves_item_ids_and_saves_interval(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
) -> None:
    created = await create(client, headers, payload(product_ids))
    before = await read(client, headers, created["id"])
    ids = {item["product_id"]: item["id"] for item in before["items"]}
    updated = {**payload(product_ids), "version": before["version"]}
    updated["buyer"] = "Comprador atualizado"
    updated["delivery_end_date"] = "2026-12-07"
    for item in updated["items"]:
        item["id"] = ids[item["product_id"]]
        item["quantity"] = "20"
        item["unit"] = "caixas"
    response = await client.put(
        f"/orders/{created['id']}", headers=headers, json=updated
    )
    assert response.status_code == 200, response.text
    after = await read(client, headers, created["id"])
    assert after["buyer"] == "Comprador atualizado"
    assert after["delivery_end_date"] == "2026-12-07"
    assert {item["product_id"]: item["id"] for item in after["items"]} == ids
    assert all(item["unit"] == "caixas" for item in after["items"])
    assert all(Decimal(item["quantity"]) == Decimal(20) for item in after["items"])


@pytest.mark.parametrize(
    "invalid",
    [
        "empty",
        "unknown-product",
        "zero",
        "negative",
        "blank-unit",
        "inverted-dates",
    ],
)
async def test_invalid_create_leaves_order_list_unchanged(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
    invalid: str,
) -> None:
    before = (await client.get("/orders", headers=headers)).json()
    data = payload(product_ids)
    make_invalid(data, invalid)
    response = await client.post("/orders", headers=headers, json=data)
    assert response.status_code == 422, response.text
    after = await client.get("/orders", headers=headers)
    assert after.status_code == 200, after.text
    assert after.json() == before


def make_invalid(data: dict, invalid: str) -> None:
    if invalid == "empty":
        data["items"] = []
    elif invalid == "unknown-product":
        data["items"][1]["product_id"] = str(uuid4())
    elif invalid == "zero":
        data["items"][1]["quantity"] = "0"
    elif invalid == "negative":
        data["items"][1]["quantity"] = "-1"
    elif invalid == "blank-unit":
        data["items"][1]["unit"] = "   "
    elif invalid == "inverted-dates":
        data["delivery_end_date"] = "2026-12-04"
    else:
        raise AssertionError(f"Unexpected case: {invalid}")


@pytest.mark.parametrize(
    "invalid",
    [
        "empty",
        "unknown-product",
        "zero",
        "negative",
        "blank-unit",
        "inverted-dates",
    ],
)
async def test_invalid_update_preserves_saved_order(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
    invalid: str,
) -> None:
    created = await create(client, headers, payload(product_ids))
    order_id = created["id"]
    before = await read(client, headers, order_id)
    ids = {item["product_id"]: item["id"] for item in before["items"]}
    data = payload(product_ids)
    data["version"] = before["version"]
    data["buyer"] = "Este nome não deve ser salvo"
    for item in data["items"]:
        item["id"] = ids[item["product_id"]]
    make_invalid(data, invalid)
    response = await client.put(f"/orders/{order_id}", headers=headers, json=data)
    assert response.status_code == 422, response.text
    assert await read(client, headers, order_id) == before


async def test_foreign_item_id_does_not_change_either_order(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
) -> None:
    first = await create(client, headers, payload(product_ids))
    second = await create(client, headers, payload(product_ids))
    before_first = await read(client, headers, first["id"])
    before_second = await read(client, headers, second["id"])
    data = payload(product_ids)
    data["version"] = before_first["version"]
    data["items"][0]["id"] = before_second["items"][0]["id"]
    response = await client.put(f"/orders/{first['id']}", headers=headers, json=data)
    assert response.status_code == 422, response.text
    assert await read(client, headers, first["id"]) == before_first
    assert await read(client, headers, second["id"]) == before_second


async def test_legacy_order_remains_readable_and_can_be_structured(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
    db_session: AsyncSession,
) -> None:
    order_id = uuid4()
    original = "  Tomate: 10 kg; Alface: 5 unidades\n"
    db_session.add(
        Order(
            id=order_id,
            buyer="Comprador antigo",
            products=original,
            conditions="Pela manhã",
            delivery_start_date=date(2026, 12, 5),
            cancelled=False,
        )
    )
    await db_session.commit()
    before = await read(client, headers, str(order_id))
    assert before["products"] == original
    assert before["items"] == []
    assert before["needs_item_structuring"] is True
    response = await client.put(
        f"/orders/{order_id}", headers=headers, json={**payload(product_ids), "version": before["version"]}
    )
    assert response.status_code == 200, response.text
    after = await read(client, headers, str(order_id))
    assert after["products"] == original
    assert len(after["items"]) == 2
    assert after["needs_item_structuring"] is False


async def test_cancel_keeps_items_readable_and_blocks_editing(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
) -> None:
    created = await create(client, headers, payload(product_ids))
    order_id = created["id"]
    before = await read(client, headers, order_id)
    response = await client.post(f"/orders/{order_id}/cancel", headers=headers)
    assert response.status_code == 200, response.text
    after = await read(client, headers, order_id)
    assert after == {**before, "cancelled": True, "version": before["version"] + 1}
    response = await client.put(
        f"/orders/{order_id}", headers=headers, json={**payload(product_ids), "version": before["version"]}
    )
    assert response.status_code == 409, response.text
    assert await read(client, headers, order_id) == after


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/orders"),
        ("POST", "/orders"),
        ("GET", "/orders/{id}"),
        ("PUT", "/orders/{id}"),
        ("POST", "/orders/{id}/cancel"),
    ],
)
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
async def test_all_order_routes_require_valid_jwt(
    client: httpx.AsyncClient,
    product_ids: tuple[str, str],
    method: str,
    path: str,
    authorization: str | None,
) -> None:
    request_headers = {} if authorization is None else {"Authorization": authorization}
    response = await client.request(
        method,
        path.format(id=uuid4()),
        headers=request_headers,
        json={**payload(product_ids), **({"version": 1} if method == "PUT" else {})},
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "method,suffix", [("GET", ""), ("PUT", ""), ("POST", "/cancel")]
)
async def test_missing_order_returns_404(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    product_ids: tuple[str, str],
    method: str,
    suffix: str,
) -> None:
    response = await client.request(
        method,
        f"/orders/{uuid4()}{suffix}",
        headers=headers,
        json={**payload(product_ids), **({"version": 1} if method == "PUT" else {})},
    )
    assert response.status_code == 404, response.text
