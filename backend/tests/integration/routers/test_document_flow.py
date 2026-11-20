import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO

import httpx
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from api import database
from api.app import app
from api.models import Document, User
from api.services.auth import AuthService
from api.storage.local import LocalDocumentStorage

BACKEND_DIR = Path(__file__).resolve().parents[3]


async def run_alembic(*args: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        check=True,
        timeout=60,
    )


@pytest.mark.asyncio
async def test_document_flow_on_migrated_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        database_url = postgres.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-key-for-document-regression")
        monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "local")
        monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
        monkeypatch.delenv("DOCUMENT_UPLOAD_MAX_BYTES", raising=False)

        await run_alembic("upgrade", "head")
        await run_alembic("check")

        engine = create_async_engine(database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "get_session_maker", lambda: sessions)
        email = "employee@example.com"
        password = "test-password"
        try:
            async with sessions.begin() as session:
                session.add(User(email=email, password_hash=AuthService.hash_password(password)))

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/documents")).status_code == 401
                login = await client.post("/auth/login", json={"email": email, "password": password})
                assert login.status_code == 200
                client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

                filename = "certificado.pdf"
                payloads = (b"%PDF-1.7 first", b"%PDF-1.7 second")
                first_upload = client.build_request(
                    "POST", "/documents", files={"file": (filename, payloads[0])}
                )
                multipart = first_upload.read()
                checkouts = []
                save = LocalDocumentStorage.save

                async def body() -> AsyncIterator[bytes]:
                    checkouts.append(("multipart", engine.pool.checkedout()))
                    yield multipart

                def save_and_measure(storage: LocalDocumentStorage, key: str, source: BinaryIO) -> None:
                    checkouts.append(("save", engine.pool.checkedout()))
                    save(storage, key, source)

                with monkeypatch.context() as patch:
                    patch.setattr(LocalDocumentStorage, "save", save_and_measure)
                    first_response = await client.post(
                        "/documents",
                        headers={"Content-Type": first_upload.headers["Content-Type"]},
                        content=body(),
                    )
                assert checkouts == [("multipart", 0), ("save", 0)]

                second_response = await client.post(
                    "/documents", files={"file": (filename, payloads[1])}
                )
                documents = []
                for upload in (first_response, second_response):
                    assert upload.status_code == 201
                    document = upload.json()
                    assert document == {"id": document["id"], "original_filename": filename}
                    documents.append(document)

                first, second = documents
                assert first["id"] != second["id"]
                listing = await client.get("/documents")
                assert listing.status_code == 200
                assert sorted(listing.json(), key=lambda item: item["id"]) == sorted(
                    documents, key=lambda item: item["id"]
                )

                for document, payload in zip(documents, payloads, strict=True):
                    for action, disposition in (("content", "inline"), ("download", "attachment")):
                        response = await client.get(f"/documents/{document['id']}/{action}")
                        assert response.status_code == 200
                        assert response.content == payload
                        assert response.headers["content-disposition"] == (
                            f"{disposition}; filename*=UTF-8''{filename}"
                        )

                async with sessions() as session:
                    keys = {
                        str(document.id): document.storage_key
                        for document in await session.scalars(select(Document))
                    }
                first_path = tmp_path / keys[first["id"]]
                second_path = tmp_path / keys[second["id"]]
                assert first_path.read_bytes() == payloads[0]
                assert second_path.read_bytes() == payloads[1]

                deleted = await client.delete(f"/documents/{first['id']}")
                assert deleted.status_code == 204
                assert deleted.content == b""
                assert (await client.get("/documents")).json() == [second]
                assert (await client.get(f"/documents/{first['id']}/content")).status_code == 404
                assert not first_path.exists()
                remaining = await client.get(f"/documents/{second['id']}/download")
                assert remaining.status_code == 200
                assert remaining.content == second_path.read_bytes() == payloads[1]
        finally:
            await engine.dispose()

        try:
            await run_alembic("downgrade", "0001_create_users")
            async with engine.connect() as connection:
                assert not await connection.run_sync(lambda conn: inspect(conn).has_table("documents"))
            async with sessions() as session:
                assert await session.scalar(select(User.email)) == email

            await run_alembic("upgrade", "head")
            async with engine.connect() as connection:
                assert await connection.run_sync(lambda conn: inspect(conn).has_table("documents"))
        finally:
            await engine.dispose()
