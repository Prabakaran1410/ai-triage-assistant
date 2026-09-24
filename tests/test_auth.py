import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import issue_jwt, verify_jwt

client = TestClient(app)


def test_issue_and_verify_jwt_round_trip():
    token = issue_jwt(user_id="u1", email="a@example.com", tenant_id="t1", role="agent")
    claims = verify_jwt(token)
    assert claims["sub"] == "u1"
    assert claims["email"] == "a@example.com"
    assert claims["tenant_id"] == "t1"
    assert claims["role"] == "agent"


def test_verify_jwt_rejects_garbage_token():
    with pytest.raises(ValueError):
        verify_jwt("not-a-real-token")


def test_triage_without_token_is_rejected():
    response = client.post("/triage", json={"message": "hello"})
    assert response.status_code == 401


def test_triage_with_invalid_token_is_rejected():
    response = client.post(
        "/triage",
        json={"message": "hello"},
        headers={"Authorization": "Bearer garbage"},
    )
    assert response.status_code == 401
