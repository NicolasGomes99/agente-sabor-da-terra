import pytest
from pydantic import ValidationError

from api.schemas.auth import LoginRequest, LoginResponse


def test_login_request_accepts_valid_credentials() -> None:
    request = LoginRequest(email="employee@example.com", password="secret")

    assert request.email == "employee@example.com"
    assert request.password == "secret"
    assert "secret" not in repr(request)


@pytest.mark.parametrize(
    "field",
    ["email", "password"],
)
def test_login_request_rejects_empty_fields(field: str) -> None:
    values = {"email": "employee@example.com", "password": "secret"}
    values[field] = ""

    with pytest.raises(ValidationError):
        LoginRequest(**values)


def test_login_request_rejects_email_longer_than_254_characters() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email=f"{'a' * 246}@test.com", password="secret")


def test_login_response_defaults_to_bearer_token_type() -> None:
    response = LoginResponse(access_token="token")

    assert response.access_token == "token"
    assert response.token_type == "bearer"


def test_login_response_rejects_unknown_token_type() -> None:
    with pytest.raises(ValidationError):
        LoginResponse.model_validate(
            {"access_token": "token", "token_type": "basic"}
        )
