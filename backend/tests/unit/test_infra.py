from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api.app import fastapi_app
from api.dependencies import get_current_user
from api.routers import infra

ENDPOINT = "/infra/smoke-test/agents"

PAYLOAD = {
    "flow": "triage",
    "confirm_inference": True,
}


@pytest.fixture
def orchestrator(monkeypatch):
    mock = AsyncMock()

    monkeypatch.setattr(infra, "orchestrate_request", mock)
    monkeypatch.setattr(
        infra,
        "get_agent_model",
        lambda: "test-model",
    )

    return mock


@pytest.fixture
def client(monkeypatch, orchestrator):
    monkeypatch.setenv("INFRA_SMOKE_TEST_ENABLED", "true")

    with TestClient(fastapi_app) as client:
        yield client


@pytest.fixture
def authenticated_client(client, monkeypatch):
    monkeypatch.setitem(
        fastapi_app.dependency_overrides,
        get_current_user,
        lambda: SimpleNamespace(),
    )

    return client


def test_requires_authentication(client, orchestrator):
    response = client.post(ENDPOINT, json=PAYLOAD)

    assert response.status_code == 401
    orchestrator.assert_not_awaited()


def test_disabled_by_default(
    authenticated_client,
    monkeypatch,
    orchestrator,
):
    monkeypatch.delenv(
        "INFRA_SMOKE_TEST_ENABLED",
        raising=False,
    )

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 404
    orchestrator.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {"flow": "triage"},
        {"flow": "triage", "confirm_inference": False},
        {"flow": "auto", "confirm_inference": True},
        {"flow": "invalid", "confirm_inference": True},
    ],
)
def test_rejects_invalid_payload(
    authenticated_client,
    orchestrator,
    payload,
):
    response = authenticated_client.post(
        ENDPOINT,
        json=payload,
    )

    assert response.status_code == 422
    orchestrator.assert_not_awaited()


def test_triage_smoke_test(
    authenticated_client,
    orchestrator,
):
    orchestrator.return_value = SimpleNamespace(
        selected_flow="triage",
        selected_agent="triage_agent",
        result=infra.TriageAnalysis.model_construct(
            summary="Solicitação fictícia de tomate.",
        ),
    )

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "model": "test-model",
        "flow": "triage",
        "agent": "triage_agent",
    }

    orchestrator.assert_awaited_once()

    request = orchestrator.await_args.args[0]

    assert request.flow == "triage"
    assert request.session_id.startswith("infra-smoke-")
    assert request.is_new_triage_message is True


def test_consultation_smoke_test(
    authenticated_client,
    orchestrator,
):
    orchestrator.return_value = SimpleNamespace(
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=infra.ConsultationResponse.model_construct(
            answer="Tomate orgânico.",
            has_sufficient_data=True,
            source_ids=[infra.SMOKE_SOURCE_ID],
        ),
    )

    response = authenticated_client.post(
        ENDPOINT,
        json={
            "flow": "consultation",
            "confirm_inference": True,
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "model": "test-model",
        "flow": "consultation",
        "agent": "consultation_agent",
    }

    request = orchestrator.await_args.args[0]

    assert request.flow == "consultation"
    assert request.sources[0].source_id == infra.SMOKE_SOURCE_ID


def test_rejects_unexpected_agent_flow(
    authenticated_client,
    orchestrator,
):
    orchestrator.return_value = SimpleNamespace(
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=None,
    )

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 502


def test_rejects_empty_triage_result(
    authenticated_client,
    orchestrator,
):
    orchestrator.return_value = SimpleNamespace(
        selected_flow="triage",
        selected_agent="triage_agent",
        result=infra.TriageAnalysis.model_construct(
            summary="",
        ),
    )

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 502


def test_rejects_consultation_without_expected_source(
    authenticated_client,
    orchestrator,
):
    orchestrator.return_value = SimpleNamespace(
        selected_flow="consultation",
        selected_agent="consultation_agent",
        result=infra.ConsultationResponse.model_construct(
            answer="Resposta fictícia.",
            has_sufficient_data=True,
            source_ids=["another-source"],
        ),
    )

    response = authenticated_client.post(
        ENDPOINT,
        json={
            "flow": "consultation",
            "confirm_inference": True,
        },
    )

    assert response.status_code == 502


def test_handles_timeout(
    authenticated_client,
    orchestrator,
):
    orchestrator.side_effect = TimeoutError()

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 504
    assert not infra._smoke_test_lock.locked()


def test_handles_failure_without_exposing_details(
    authenticated_client,
    orchestrator,
    caplog,
):
    orchestrator.side_effect = RuntimeError(
        "sensitive-provider-information"
    )

    response = authenticated_client.post(
        ENDPOINT,
        json=PAYLOAD,
    )

    assert response.status_code == 502

    assert response.json() == {
        "detail": "Agent smoke test failed.",
    }

    assert "sensitive-provider-information" not in response.text
    assert "sensitive-provider-information" not in caplog.text
    assert not infra._smoke_test_lock.locked()


def test_smoke_requests_have_distinct_sessions():
    first = infra.build_smoke_test_request("triage")
    second = infra.build_smoke_test_request("triage")

    assert first.session_id != second.session_id