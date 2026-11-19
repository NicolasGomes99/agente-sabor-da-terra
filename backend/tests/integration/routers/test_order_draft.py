"""HTTP contract over the same real PostgreSQL cases as the service tests."""

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from api import database
from api.app import app
from api.models.order_draft import OrderDraft
from api.models.solicitation import Solicitation, SolicitationStatus
from api.repositories.user import UserRepository
from api.services.auth import AuthService
from api.services.user import UserService
from tests.integration.services.test_order_draft import case as case  # noqa: PLC0414

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def http(case, monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "order-draft-http-tests-secret-at-least-32-bytes"
    )
    monkeypatch.setattr(database, "get_session_maker", lambda: case.factory)
    async with case.factory() as session:
        auth = AuthService(UserService(UserRepository(session)))
        owner_token = auth.create_access_token(case.owner)
        other_token = auth.create_access_token(case.other_user)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield (
            client,
            {"Authorization": f"Bearer {owner_token}"},
            {
                "Authorization": f"Bearer {other_token}",
            },
        )


def urls(case, draft_id=None):
    prefix = (
        f"/solicitations/{case.solicitation_id}"
        if case.solicitation_id
        else f"/chat/sessions/{case.chat_id}"
    )
    return (
        f"{prefix}/order-draft",
        f"{prefix}/order-drafts/{draft_id or case.draft_id}/confirm",
    )


async def test_read_confirm_and_reopen_preserves_order(http, case):
    client, headers, _ = http
    read_url, confirm_url = urls(case)
    before = await client.get(read_url, headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["draft"]["id"] == str(case.draft_id)
    assert before.json()["draft"]["version"] == 1
    assert before.json()["draft"]["data"] == case.data.model_dump(mode="json")
    assert before.json()["order"] is None

    payload = case.confirmation().model_dump(mode="json")
    confirmed = await client.post(confirm_url, headers=headers, json=payload)
    assert confirmed.status_code == 201, confirmed.text
    order = confirmed.json()
    assert order["session_id"] == str(case.chat_id)
    assert order["buyer"] == "Mercado Bom Preço"
    assert order["delivery_start_date"] == "2026-11-06"
    assert order["delivery_end_date"] is None
    assert len(order["items"]) == 1
    assert order["items"][0]["product"]["id"] == str(case.products[0])
    reopened = await client.get(read_url, headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["order"]["id"] == order["id"]
    assert reopened.json()["draft"]["confirmed_order_id"] == order["id"]
    repeated = await client.post(confirm_url, headers=headers, json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == order["id"]


@pytest.mark.parametrize("token", [None, "invalid-token"])
async def test_read_and_confirmation_require_valid_jwt(http, case, token):
    client, _, _ = http
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    read_url, confirm_url = urls(case)
    assert (await client.get(read_url, headers=headers)).status_code == 401
    result = await client.post(
        confirm_url, headers=headers, json=case.confirmation().model_dump(mode="json")
    )
    assert result.status_code == 401
    await case.assert_no_order()


async def test_private_owner_only_and_shared_triage(http, case):
    client, _, other = http
    read_url, confirm_url = urls(case)
    read = await client.get(read_url, headers=other)
    confirmed = await client.post(
        confirm_url, headers=other, json=case.confirmation().model_dump(mode="json")
    )
    if case.solicitation_id:
        assert read.status_code == 200, read.text
        assert confirmed.status_code == 201, confirmed.text
    else:
        assert read.status_code == confirmed.status_code == 404
        await case.assert_no_order()


@pytest.mark.parametrize(
    "invalid", ["explicit", "version-missing", "version-stale", "product", "item"]
)
async def test_invalid_confirmation_returns_error_and_preserves_database(
    http, case, invalid
):
    client, headers, _ = http
    payload = case.confirmation().model_dump(mode="json")
    expected = 422
    if invalid == "explicit":
        payload["confirmed"] = False
    elif invalid == "version-missing":
        del payload["draft_version"]
    elif invalid == "version-stale":
        payload["draft_version"] = 2
        expected = 409
    elif invalid == "product":
        payload["items"][0]["product_id"] = str(uuid4())
    else:
        payload["items"][0]["draft_item_id"] = str(uuid4())
    result = await client.post(urls(case)[1], headers=headers, json=payload)
    assert result.status_code == expected, result.text
    if invalid == "version-stale":
        assert result.json()["detail"]["code"] == "order_draft_version_conflict"
    await case.assert_no_order()


async def test_different_confirmation_reports_existing_order_link(http, case):
    client, headers, _ = http
    payload = case.confirmation().model_dump(mode="json")
    confirm_url = urls(case)[1]
    first = await client.post(confirm_url, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    payload["buyer"] = "Outra confirmação"
    conflict = await client.post(confirm_url, headers=headers, json=payload)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "order_already_confirmed"
    assert conflict.json()["detail"]["order_id"] == first.json()["id"]


async def test_missing_draft_is_not_found(http, case):
    client, headers, _ = http
    result = await client.post(
        urls(case, uuid4())[1],
        headers=headers,
        json=case.confirmation().model_dump(mode="json"),
    )
    assert result.status_code == 404, result.text
    await case.assert_no_order()


async def test_conversation_without_draft_returns_empty_context(http, case):
    client, headers, _ = http
    async with case.factory.begin() as session:
        draft = await session.get(OrderDraft, case.draft_id)
        await session.delete(draft)
    result = await client.get(urls(case)[0], headers=headers)
    assert result.status_code == 200, result.text
    assert result.json() == {"draft": None, "order": None}


async def test_cancelled_order_remains_visible_after_triage_is_finished(http, case):
    client, headers, _ = http
    read_url, confirm_url = urls(case)
    payload = case.confirmation().model_dump(mode="json")
    first = await client.post(confirm_url, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    order_id = first.json()["id"]
    cancelled = await client.post(f"/orders/{order_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    if case.solicitation_id:
        async with case.factory.begin() as session:
            solicitation = await session.get(Solicitation, case.solicitation_id)
            solicitation.status = SolicitationStatus.FINISHED
        rejected = await client.post(confirm_url, headers=headers, json=payload)
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["detail"]["code"] == "solicitation_finished"
    reopened = await client.get(read_url, headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["order"]["id"] == order_id
    assert reopened.json()["order"]["cancelled"] is True
