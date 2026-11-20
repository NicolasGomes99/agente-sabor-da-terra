import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from api.models import Producer, ProducerProduct, Product, User
from api.routers import auth, producer
from api.services.auth import JWT_ALGORITHM, AuthService

pytestmark = pytest.mark.asyncio(loop_scope="function")
BACKEND_DIR = Path(__file__).resolve().parents[3]
TEST_SECRET_KEY = "test-producer-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "test-password"


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    sessions = async_sessionmaker(
        bind=await db_session.connection(), expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: sessions)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    previous_overrides = fastapi_app.dependency_overrides.copy()
    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
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


async def seed_catalog(session: AsyncSession) -> list[dict]:
    alface = Product(id=uuid4(), name="Alface")
    coentro = Product(id=uuid4(), name="Coentro")
    data = [
        {
            "id": uuid4(), "code": "P001", "name": "Ana Silva", "cpf": "01234567890",
            "active": True, "phone": "81999990000", "email": "ana@example.com",
            "address": "Rua das Flores, 10", "municipality": "Caruaru",
        },
        {
            "id": uuid4(), "code": "P002", "name": "Bruno Silva", "cpf": "12345678901",
            "active": False, "phone": None, "email": None, "address": None, "municipality": None,
        },
        {
            "id": uuid4(), "code": "P003", "name": "Clara Silva", "cpf": "23456789012",
            "active": True, "phone": None, "email": None, "address": None, "municipality": None,
        },
    ]
    session.add_all([Producer(**values) for values in reversed(data)])
    session.add_all([coentro, alface])
    await session.flush()
    session.add_all([
        ProducerProduct(producer_id=data[0]["id"], product_id=coentro.id),
        ProducerProduct(producer_id=data[1]["id"], product_id=alface.id),
        ProducerProduct(producer_id=data[0]["id"], product_id=alface.id),
    ])
    await session.flush()
    alface_response = {"id": str(alface.id), "name": "Alface"}
    coentro_response = {"id": str(coentro.id), "name": "Coentro"}
    return [
        {**values, "id": str(values["id"]), "products": products}
        for values, products in zip(data, [[alface_response, coentro_response], [alface_response], []])
    ]


@pytest_asyncio.fixture
async def catalog(db_session: AsyncSession) -> list[dict]:
    expected = await seed_catalog(db_session)
    db_session.expunge_all()
    return expected


async def test_list_producers_returns_data_and_products(
    client: httpx.AsyncClient, headers: dict[str, str], catalog: list[dict],
) -> None:
    response = await client.get("/producers", headers=headers)

    assert response.status_code == 200
    assert response.json() == catalog


async def test_list_producers_includes_inactive_and_unassociated_producers(
    client: httpx.AsyncClient, headers: dict[str, str], catalog: list[dict],
) -> None:
    response = await client.get("/producers", headers=headers)

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()}
    assert by_id[catalog[1]["id"]] == catalog[1]
    assert by_id[catalog[1]["id"]]["active"] is False
    assert by_id[catalog[2]["id"]]["products"] == []


async def test_list_producers_returns_empty_list(
    client: httpx.AsyncClient, headers: dict[str, str],
) -> None:
    response = await client.get("/producers", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_list_producers_filters_by_product(
    client: httpx.AsyncClient, headers: dict[str, str], catalog: list[dict],
) -> None:
    response = await client.get(
        "/producers", params={"product_id": catalog[0]["products"][0]["id"]}, headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == catalog[:2]


@pytest.mark.parametrize("existing_product", [True, False])
async def test_list_producers_returns_empty_list_for_product_without_suppliers(
    client: httpx.AsyncClient, headers: dict[str, str], catalog: list[dict],
    db_session: AsyncSession, existing_product: bool,
) -> None:
    product_id = uuid4()
    if existing_product:
        db_session.add(Product(id=product_id, name="Tomate"))
        await db_session.flush()

    response = await client.get("/producers", params={"product_id": str(product_id)}, headers=headers)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("producer_index", [0, 1, 2])
async def test_get_producer_returns_data_and_products(
    client: httpx.AsyncClient, headers: dict[str, str], catalog: list[dict], producer_index: int,
) -> None:
    expected = catalog[producer_index]

    response = await client.get(f"/producers/{expected['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() == expected


async def test_get_producer_returns_404_for_unknown_id(
    client: httpx.AsyncClient, headers: dict[str, str],
) -> None:
    response = await client.get(f"/producers/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Producer not found."}


@pytest.mark.parametrize(("path", "location"), [
    ("/producers/invalid-uuid", ["path", "producer_id"]),
    ("/producers?product_id=invalid-uuid", ["query", "product_id"]),
])
async def test_producer_routes_reject_invalid_uuids(
    client: httpx.AsyncClient, headers: dict[str, str], path: str, location: list[str],
) -> None:
    response = await client.get(path, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == location


@pytest.mark.parametrize("path", [
    "/producers", f"/producers?product_id={uuid4()}", f"/producers/{uuid4()}",
])
@pytest.mark.parametrize("token_kind", ["missing", "invalid", "expired"])
async def test_producer_routes_require_valid_token(
    client: httpx.AsyncClient, headers: dict[str, str], path: str, token_kind: str,
) -> None:
    request_headers = {}
    if token_kind == "invalid":
        request_headers["Authorization"] = "Bearer invalid-token"
    elif token_kind == "expired":
        payload = jwt.decode(
            headers["Authorization"].removeprefix("Bearer "), TEST_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        payload["iat"] = datetime.now(UTC) - timedelta(hours=2)
        payload["exp"] = datetime.now(UTC) - timedelta(hours=1)
        token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=JWT_ALGORITHM)
        request_headers["Authorization"] = f"Bearer {token}"

    response = await client.get(path, headers=request_headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_producers_remain_available_after_app_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET_KEY)
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", url)
        await asyncio.to_thread(
            subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, check=True, timeout=60,
        )
        engine = create_async_engine(url)
        email = "restart@example.com"
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions.begin() as session:
                expected = await seed_catalog(session)
                session.add(User(email=email, password_hash=AuthService.hash_password(TEST_PASSWORD)))

            for _ in range(2):
                await engine.dispose()
                engine = create_async_engine(url)
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                monkeypatch.setattr(database, "get_session_maker", lambda factory=sessions: factory)
                restarted_app = FastAPI()
                restarted_app.include_router(auth.router)
                restarted_app.include_router(producer.router)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=restarted_app), base_url="http://test",
                ) as restarted_client:
                    login = await restarted_client.post(
                        "/auth/login", json={"email": email, "password": TEST_PASSWORD},
                    )
                    assert login.status_code == 200
                    request_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                    listing = await restarted_client.get("/producers", headers=request_headers)
                    assert listing.status_code == 200
                    assert listing.json() == expected
                    for item in expected:
                        detail = await restarted_client.get(
                            f"/producers/{item['id']}", headers=request_headers,
                        )
                        assert detail.status_code == 200
                        assert detail.json() == item
                    filtered = await restarted_client.get(
                        "/producers", params={"product_id": expected[0]["products"][0]["id"]},
                        headers=request_headers,
                    )
                    assert filtered.status_code == 200
                    assert filtered.json() == expected[:2]
        finally:
            await engine.dispose()


async def test_producer_openapi_documents_responses() -> None:
    schema = fastapi_app.openapi()
    listing = schema["paths"]["/producers"]["get"]
    detail = schema["paths"]["/producers/{producer_id}"]["get"]
    response_ref = {"$ref": "#/components/schemas/ProducerResponse"}
    assert listing["responses"]["200"]["content"]["application/json"]["schema"]["items"] == response_ref
    assert detail["responses"]["200"]["content"]["application/json"]["schema"] == response_ref
    parameter = next(item for item in listing["parameters"] if item["name"] == "product_id")
    assert parameter["in"] == "query"
    assert parameter["required"] is False
    assert {"type": "string", "format": "uuid"} in parameter["schema"]["anyOf"]
    for operation in (listing, detail):
        assert operation["security"] == [{"OAuth2PasswordBearer": []}]
        unauthorized = operation["responses"]["401"]
        assert "WWW-Authenticate" in unauthorized["headers"]
        assert "detail" in unauthorized["content"]["application/json"]["schema"]["required"]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HTTPValidationError"
        }
    assert "detail" in detail["responses"]["404"]["content"]["application/json"]["schema"]["required"]
    producer_schema = schema["components"]["schemas"]["ProducerResponse"]
    assert "products" in producer_schema["required"]
    assert "active" in producer_schema["required"]
    assert producer_schema["properties"]["products"]["items"] == {
        "$ref": "#/components/schemas/ProductResponse"
    }
