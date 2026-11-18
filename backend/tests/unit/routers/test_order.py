from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import app, fastapi_app
from api.dependencies import get_current_user, get_order_service
from api.models.order import Order
from api.models.user import User
from api.services.order import OrderService

ORDER_ID = uuid4()
PAYLOAD = {
    "buyer": "Migration review test",
    "products": "Tomato: 10 kg",
    "conditions": "Morning delivery",
    "delivery_start_date": "2026-12-05",
    "delivery_end_date": None,
}


@pytest.fixture
def order_service(monkeypatch: pytest.MonkeyPatch) -> Mock:
    order = Order(
        id=ORDER_ID,
        session_id=None,
        buyer=PAYLOAD["buyer"],
        products=PAYLOAD["products"],
        conditions=PAYLOAD["conditions"],
        delivery_start_date=date(2026, 12, 5),
        delivery_end_date=None,
        cancelled=False,
    )
    service = Mock(spec=OrderService)
    for name in ("create_order", "get_order", "update_order"):
        setattr(service, name, AsyncMock(return_value=order))
    service.list_orders = AsyncMock(return_value=[order])
    cancelled = Order(
        id=ORDER_ID,
        **{**PAYLOAD, "delivery_start_date": date(2026, 12, 5)},
        session_id=None,
        cancelled=True,
    )
    service.cancel_order = AsyncMock(return_value=cancelled)
    user = User(id=uuid4(), email="test@example.com", password_hash="test")
    monkeypatch.setitem(
        fastapi_app.dependency_overrides, get_current_user, lambda: user
    )
    monkeypatch.setitem(
        fastapi_app.dependency_overrides, get_order_service, lambda: service
    )
    return service


@pytest_asyncio.fixture
async def client(order_service: Mock) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "expected_status", "service_method"),
    [
        ("POST", "/orders", 201, "create_order"),
        ("GET", "/orders", 200, "list_orders"),
        ("GET", f"/orders/{ORDER_ID}", 200, "get_order"),
        ("PUT", f"/orders/{ORDER_ID}", 200, "update_order"),
        ("POST", f"/orders/{ORDER_ID}/cancel", 200, "cancel_order"),
    ],
)
async def test_order_routes_remain_registered(
    client: httpx.AsyncClient,
    order_service: Mock,
    method: str,
    path: str,
    expected_status: int,
    service_method: str,
) -> None:
    response = await client.request(method, path, json=PAYLOAD)
    assert response.status_code == expected_status
    getattr(order_service, service_method).assert_awaited_once()
    body = response.json()
    if isinstance(body, list):
        assert len(body) == 1
        body = body[0]
    assert body["id"] == str(ORDER_ID)
    assert body["cancelled"] is (service_method == "cancel_order")


@pytest.mark.asyncio
async def test_orders_still_require_authentication(
    client: httpx.AsyncClient,
    order_service: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(fastapi_app.dependency_overrides, get_current_user)
    response = await client.get("/orders")
    assert response.status_code == 401
    order_service.list_orders.assert_not_awaited()


def test_merge_preserves_existing_routes_and_put_in_cors() -> None:
    paths = fastapi_app.openapi()["paths"]
    assert {
        "/auth/login",
        "/documents",
        "/chat/sessions",
        "/products",
        "/producers",
        "/orders",
    } <= set(paths)
    assert "PUT" in app.allow_methods


def test_order_dependency_injects_the_session() -> None:
    session = Mock(spec=AsyncSession)
    service = get_order_service(session)
    assert isinstance(service, OrderService)
    assert service.repository.session is session
