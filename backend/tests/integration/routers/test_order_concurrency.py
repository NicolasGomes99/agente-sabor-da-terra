"""HTTP regression tests using independent real PostgreSQL sessions per request."""
import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from uuid import uuid4
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from api import database
from api.app import app
from api.models.order import Order
from api.models.order_item import OrderItem
from api.models.product import Product
from api.models.user import User
from api.services.auth import AuthService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def api(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict, tuple[str, str]]]:
    # Unlike the shared savepoint fixture, commits here are visible to other sessions.
    # Each HTTP request opens its own connection through the real get_db dependency.
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "get_session_maker", lambda: factory)
    monkeypatch.setenv("JWT_SECRET_KEY", "order-concurrency-tests-only-secret-at-least-32-bytes")
    user_id, first, second = uuid4(), uuid4(), uuid4()
    email, password = f"{user_id}@example.com", "concurrency-test-password"
    async with factory.begin() as session:
        session.add(User(id=user_id, email=email, password_hash=AuthService.hash_password(password)))
        session.add_all([Product(id=first, name=f"Tomate {first}"), Product(id=second, name=f"Alface {second}")])
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            login = await client.post("/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            yield client, headers, (str(first), str(second))
    finally:
        async with factory.begin() as session:
            order_ids = select(OrderItem.order_id).where(OrderItem.product_id.in_([first, second]))
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))
            await session.execute(delete(Product).where(Product.id.in_([first, second])))
            await session.execute(delete(User).where(User.id == user_id))

def normalize_order(snapshot: dict) -> dict:
    result = deepcopy(snapshot)

    for item in result["items"]:
        item["quantity"] = Decimal(item["quantity"])

    result["items"].sort(key=lambda item: item["id"])

    return result

def edit(snapshot: dict) -> dict:
    return {
        key: deepcopy(snapshot[key])
        for key in ("buyer", "conditions", "delivery_start_date", "delivery_end_date", "version")
    } | {
        "items": [
            {key: item[key] for key in ("id", "product_id", "quantity", "unit")}
            for item in snapshot["items"]
        ]
    }


async def create(client: httpx.AsyncClient, headers: dict, products: tuple[str, str]) -> dict:
    response = await client.post("/orders", headers=headers, json={
        "buyer": "Concurrency test", "delivery_start_date": "2026-12-05",
        "items": [{"product_id": products[0], "quantity": "2", "unit": "kg"}],
    })
    assert response.status_code == 201, response.text
    assert response.json()["version"] == 1
    assert response.json()["session_id"] is None
    return response.json()


async def test_stale_form_cannot_delete_item_added_by_another_editor(api) -> None:
    client, headers, products = api
    created = await create(client, headers, products)
    url = f"/orders/{created['id']}"
    editor_a = (await client.get(url, headers=headers)).json()
    editor_b = (await client.get(url, headers=headers)).json()
    original_id = editor_a["items"][0]["id"]

    first = edit(editor_a)
    first["items"].append({"product_id": products[1], "quantity": "5", "unit": "un"})
    saved = await client.put(url, headers=headers, json=first)
    assert saved.status_code == 200, saved.text
    latest = saved.json()
    assert latest["version"] == 2
    assert len(latest["items"]) == 2

    stale = edit(editor_b)
    stale["items"][0]["unit"] = "caixa"
    rejected = await client.put(url, headers=headers, json=stale)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "order_version_conflict"
    actual = (await client.get(url, headers=headers)).json()
    assert normalize_order(actual) == normalize_order(latest)

    refreshed = edit(latest)
    next(item for item in refreshed["items"] if item["id"] == original_id)["unit"] = "caixa"
    accepted = await client.put(url, headers=headers, json=refreshed)
    assert accepted.status_code == 200, accepted.text
    final = accepted.json()
    assert final["version"] == 3
    assert {item["id"] for item in final["items"]} == {item["id"] for item in latest["items"]}
    assert next(item for item in final["items"] if item["id"] == original_id)["unit"] == "caixa"


async def test_simultaneous_writes_with_same_version_have_one_winner(api) -> None:
    client, headers, products = api
    created = await create(client, headers, products)
    url = f"/orders/{created['id']}"
    first, second = edit(created), edit(created)
    first["items"].append({"product_id": products[1], "quantity": "3", "unit": "un"})
    second["items"][0]["unit"] = "caixa"
    responses = await asyncio.gather(
        client.put(url, headers=headers, json=first),
        client.put(url, headers=headers, json=second),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert winner["version"] == 2
    actual = (await client.get(url, headers=headers)).json()
    assert normalize_order(actual) == normalize_order(winner)


async def test_put_without_version_is_rejected_without_changes(api) -> None:
    client, headers, products = api
    created = await create(client, headers, products)
    url = f"/orders/{created['id']}"
    data = edit(created)
    del data["version"]
    response = await client.put(url, headers=headers, json=data)
    assert response.status_code == 422
    actual = (await client.get(url, headers=headers)).json()
    assert normalize_order(actual) == normalize_order(created)


async def test_cancellation_changes_version_and_blocks_open_form(api) -> None:
    client, headers, products = api
    created = await create(client, headers, products)
    url = f"/orders/{created['id']}"
    response = await client.post(f"{url}/cancel", headers=headers)
    assert response.status_code == 200
    cancelled = response.json()
    assert cancelled["version"] == created["version"] + 1
    assert (
    normalize_order(cancelled)["items"]
    == normalize_order(created)["items"]
    )
    rejected = await client.put(url, headers=headers, json=edit(created))
    assert rejected.status_code == 409
    repeated = await client.post(f"{url}/cancel", headers=headers)
    assert repeated.json() == cancelled
