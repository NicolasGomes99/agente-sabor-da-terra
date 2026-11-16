import pytest

from api.config import get_cors_allowed_origins


def test_get_cors_allowed_origins_parses_comma_separated_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " http://localhost:5173, http://127.0.0.1:5173 ",
    )

    assert get_cors_allowed_origins() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_get_cors_allowed_origins_ignores_empty_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ", http://localhost:5173, ,")

    assert get_cors_allowed_origins() == ["http://localhost:5173"]


def test_get_cors_allowed_origins_returns_empty_list_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert get_cors_allowed_origins() == []
