from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from api import database
from api.app import app, fastapi_app
from api.database import get_db
from api.models import Base, Product, User
from api.routers import auth, product
from api.services.auth import JWT_ALGORITHM, AuthService

pytestmark = pytest.mark.asyncio(loop_scope="function")
TEST_SECRET_KEY = "test-product-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "test-password"


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    sessions = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    previous_overrides = fastapi_app.dependency_overrides.copy()
    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
        fastapi_app.dependency_overrides.update(previous_overrides)


@pytest_asyncio.fixture
async def headers(client: httpx.AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    email = f"{uuid4()}@example.com"
    db_session.add(User(email=email, password_hash=AuthService.hash_password(TEST_PASSWORD)))
    await db_session.flush()
    response = await client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_list_products_returns_ids_and_names(
    client: httpx.AsyncClient, headers: dict[str, str], db_session: AsyncSession
) -> None:
    coentro_id, alface_id = uuid4(), uuid4()
    db_session.add_all([
        Product(id=coentro_id, name="Coentro"),
        Product(id=alface_id, name="Alface"),
    ])
    await db_session.flush()

    response = await client.get("/products", headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {"id": str(alface_id), "name": "Alface"},
        {"id": str(coentro_id), "name": "Coentro"},
    ]


async def test_list_products_returns_empty_list(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/products", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_get_product_returns_existing_product(
    client: httpx.AsyncClient, headers: dict[str, str], db_session: AsyncSession
) -> None:
    product_id = uuid4()
    db_session.add(Product(id=product_id, name="Alface"))
    await db_session.flush()

    response = await client.get(f"/products/{product_id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"id": str(product_id), "name": "Alface"}


async def test_get_product_returns_404_for_unknown_id(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get(f"/products/{uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found."}


async def test_get_product_rejects_invalid_uuid(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/products/invalid-uuid", headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "product_id"]


@pytest.mark.parametrize("path", ["/products", f"/products/{uuid4()}"])
@pytest.mark.parametrize("token_kind", ["missing", "invalid", "expired"])
async def test_product_routes_require_valid_token(
    client: httpx.AsyncClient, path: str, token_kind: str
) -> None:
    request_headers = {}
    if token_kind == "invalid":
        request_headers["Authorization"] = "Bearer invalid-token"
    elif token_kind == "expired":
        now = datetime.now(UTC)
        token = jwt.encode(
            {"sub": str(uuid4()), "iat": now - timedelta(hours=2),
             "exp": now - timedelta(hours=1), "type": "access"},
            TEST_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )
        request_headers["Authorization"] = f"Bearer {token}"

    response = await client.get(path, headers=request_headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_products_remain_available_after_app_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        url = postgres.get_connection_url(driver="asyncpg")
        engine = create_async_engine(url)
        product_id = uuid4()
        email = "restart@example.com"
        try:
            async with engine.begin() as connection:
                await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
                await connection.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions.begin() as session:
                session.add_all([
                    Product(id=product_id, name="Alface"),
                    User(email=email, password_hash=AuthService.hash_password(TEST_PASSWORD)),
                ])
            # Recreate both the application and connection pool against the same database.
            for _ in range(2):
                await engine.dispose()
                engine = create_async_engine(url)
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                monkeypatch.setattr(database, "get_session_maker", lambda factory=sessions: factory)
                restarted_app = FastAPI()
                restarted_app.include_router(auth.router)
                restarted_app.include_router(product.router)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=restarted_app), base_url="http://test"
                ) as client:
                    login = await client.post(
                        "/auth/login", json={"email": email, "password": TEST_PASSWORD}
                    )
                    assert login.status_code == 200
                    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                    expected = {"id": str(product_id), "name": "Alface"}
                    listing = await client.get("/products", headers=headers)
                    detail = await client.get(f"/products/{product_id}", headers=headers)
                    assert listing.status_code == detail.status_code == 200
                    assert listing.json() == [expected]
                    assert detail.json() == expected
        finally:
            await engine.dispose()


async def test_product_openapi_documents_responses() -> None:
    schema = fastapi_app.openapi()
    listing = schema["paths"]["/products"]["get"]
    detail = schema["paths"]["/products/{product_id}"]["get"]
    response_ref = {"$ref": "#/components/schemas/ProductResponse"}
    assert listing["responses"]["200"]["content"]["application/json"]["schema"]["items"] == (
        response_ref
    )
    assert detail["responses"]["200"]["content"]["application/json"]["schema"] == response_ref
    for operation in (listing, detail):
        assert operation["security"] == [{"OAuth2PasswordBearer": []}]
        unauthorized = operation["responses"]["401"]
        assert "WWW-Authenticate" in unauthorized["headers"]
        assert "detail" in unauthorized["content"]["application/json"]["schema"]["required"]
    assert "detail" in detail["responses"]["404"]["content"]["application/json"]["schema"]["required"]
