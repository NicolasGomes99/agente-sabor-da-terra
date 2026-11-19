from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api import database
from api.app import fastapi_app as app
from api.database import get_db
from api.models import Order, OrderItem, Producer, ProducerProduct, Product
from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService

TEST_SECRET_KEY = "test-secret-key-with-at-least-32-bytes-long"

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(loop_scope="function")
async def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    auth_sessions = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: auth_sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


async def create_user_headers(db_session: AsyncSession) -> dict[str, str]:
    repository = UserRepository(db_session)
    auth_service = AuthService(
        UserService(repository),
        secret_key=TEST_SECRET_KEY,
    )
    user = await repository.create(
        f"{uuid4()}@example.com",
        auth_service.hash_password("password"),
    )
    token = auth_service.create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def setup(db_session: AsyncSession) -> SimpleNamespace:
    product = Product(name="Tomate")
    producer = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    db_session.add_all([product, producer])
    await db_session.flush()
    db_session.add(ProducerProduct(producer_id=producer.id, product_id=product.id))

    order = Order(
        buyer="Mercado",
        products="",
        conditions="",
        delivery_start_date=date(2026, 11, 4),
        delivery_end_date=date(2026, 11, 8),
    )
    db_session.add(order)
    await db_session.flush()
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=Decimal(100),
        unit="kg",
    )
    db_session.add(item)
    await db_session.commit()

    return SimpleNamespace(order=order, item=item, producer=producer)


def lot_payload(producer_id: UUID, **overrides) -> dict:
    return {
        "producer_id": str(producer_id),
        "quantity": "10",
        "unit": "kg",
        "delivery_date": "2026-11-04",
        "availability_confirmed": True,
        **overrides,
    }


async def test_create_lot_requires_jwt(
    client: httpx.AsyncClient,
    setup: SimpleNamespace,
) -> None:
    response = await client.post(
        f"/orders/{setup.order.id}/items/{setup.item.id}/lots",
        json=lot_payload(setup.producer.id),
    )
    assert response.status_code == 401


async def test_create_lot(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    setup: SimpleNamespace,
) -> None:
    headers = await create_user_headers(db_session)
    response = await client.post(
        f"/orders/{setup.order.id}/items/{setup.item.id}/lots",
        headers=headers,
        json=lot_payload(setup.producer.id),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["producer"]["name"] == "Ana Silva"
    assert body["availability_confirmed"] is True


async def test_create_lot_with_inactive_producer_returns_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    setup: SimpleNamespace,
) -> None:
    headers = await create_user_headers(db_session)
    inactive = Producer(code="P002", name="João", cpf="12345678901", active=False)
    db_session.add(inactive)
    await db_session.flush()
    db_session.add(ProducerProduct(producer_id=inactive.id, product_id=setup.item.product_id))
    await db_session.commit()

    response = await client.post(
        f"/orders/{setup.order.id}/items/{setup.item.id}/lots",
        headers=headers,
        json=lot_payload(inactive.id),
    )
    assert response.status_code == 422


async def test_update_missing_lot_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    response = await client.put(
        f"/lots/{uuid4()}",
        headers=headers,
        json=lot_payload(uuid4()),
    )
    assert response.status_code == 404


async def test_delete_missing_lot_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_user_headers(db_session)
    response = await client.delete(f"/lots/{uuid4()}", headers=headers)
    assert response.status_code == 404
