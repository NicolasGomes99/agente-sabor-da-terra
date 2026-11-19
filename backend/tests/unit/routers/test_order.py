from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from api.app import app, fastapi_app
from api.dependencies import get_current_user, get_order_service
from api.models.order import Order
from api.models.order_item import OrderItem
from api.models.product import Product
from api.models.user import User
from api.services.order import OrderService

ORDER_ID = uuid4()
PRODUCT_ID = uuid4()
ITEM_ID = uuid4()
PAYLOAD = {
    "buyer": "Migration review test",
    "conditions": "Morning delivery",
    "delivery_start_date": "2026-12-05",
    "delivery_end_date": None,
    "items": [
        {
            "product_id": str(PRODUCT_ID),
            "quantity": "10",
            "unit": "kg",
        }
    ],
}


@pytest.fixture
def order_service(monkeypatch: pytest.MonkeyPatch) -> Mock:
    product = Product(
        id=PRODUCT_ID,
        name="Tomate",
    )

    def make_order(*, cancelled: bool) -> Order:
        return Order(
            id=ORDER_ID,
            session_id=None,
            buyer=PAYLOAD["buyer"],
            products="",
            conditions=PAYLOAD["conditions"],
            delivery_start_date=date(2026, 12, 5),
            delivery_end_date=None,
            cancelled=cancelled,
            items=[
                OrderItem(
                    id=ITEM_ID,
                    product_id=PRODUCT_ID,
                    product=product,
                    quantity=Decimal(10),
                    unit="kg",
                )
            ],
        )

    order = make_order(cancelled=False)
    cancelled_order = make_order(cancelled=True)

    service = Mock(spec=OrderService)

    for name in (
        "create_order",
        "get_order",
        "update_order",
    ):
        setattr(
            service,
            name,
            AsyncMock(return_value=order),
        )

    service.list_orders = AsyncMock(
        return_value=[order],
    )

    service.cancel_order = AsyncMock(
        return_value=cancelled_order,
    )

    user = User(
        id=uuid4(),
        email="test@example.com",
        password_hash="test",
    )

    monkeypatch.setitem(
        fastapi_app.dependency_overrides,
        get_current_user,
        lambda: user,
    )

    monkeypatch.setitem(
        fastapi_app.dependency_overrides,
        get_order_service,
        lambda: service,
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
    if method == "PUT":
        payload = {
            **PAYLOAD,
            "items": [
                {
                    **PAYLOAD["items"][0],
                    "id": str(ITEM_ID),
                }
            ],
        }
        response = await client.request(method,path, json=payload)

    elif method == "POST" and path == "/orders":
        response = await client.request(method, path, json=PAYLOAD)

    else:
        response = await client.request(method, path)

    assert response.status_code == expected_status
    getattr(order_service, service_method).assert_awaited_once()
    body = response.json()
    if isinstance(body, list):
        assert len(body) == 1
        body = body[0]
    assert body["id"] == str(ORDER_ID)
    assert body["cancelled"] is (service_method == "cancel_order")
    assert body["items"][0]["id"] == str(ITEM_ID)
    assert body["items"][0]["product_id"] == str(PRODUCT_ID)
    assert body["items"][0]["product"]["name"] == "Tomate"


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
