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


def test_authorization_url_uses_the_sdks_real_parameter_names(monkeypatch):
    """Regression: the WorkOS SDK takes `organization`, not `organization_id`.

    A wrong keyword only fails at request time (a 500 on /auth/login), so pin
    it here against the SDK's actual signature instead of a mock.
    """
    import inspect

    from workos.sso import SSO

    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_dummy")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_dummy")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        from app.services.auth import get_authorization_url

        params = inspect.signature(SSO.get_authorization_url).parameters
        assert "organization" in params and "organization_id" not in params

        url = get_authorization_url("org_test", "https://example.com/cb", "state123")
        assert url.startswith("https://api.workos.com/sso/authorize")
        assert "organization=org_test" in url
    finally:
        get_settings.cache_clear()


def test_callback_surfaces_workos_error_instead_of_a_422():
    response = client.get(
        "/auth/callback",
        params={
            "error": "profile_not_allowed_outside_organization",
            "error_description": "Profile domain does not belong to the target Organization.",
        },
    )
    assert response.status_code == 400
    assert "does not belong to the target Organization" in response.json()["detail"]


def test_callback_without_code_or_error_is_a_400():
    assert client.get("/auth/callback").status_code == 400


def test_profile_exchange_uses_keyword_code_argument():
    """Regression: SSO.get_profile_and_token is keyword-only (`*, code=...`).

    Passing the code positionally raises TypeError only when a real login
    arrives, so pin it against the SDK's signature.
    """
    import inspect

    from workos.sso import SSO

    param = inspect.signature(SSO.get_profile_and_token).parameters["code"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def _token_issued_at(offset_seconds: int) -> str:
    """A token whose iat/exp are shifted relative to now, signed like ours."""
    import datetime as dt

    import jwt

    from app.core.config import get_settings
    from app.services.auth import ALGORITHM

    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset_seconds)
    return jwt.encode(
        {
            "sub": "u1",
            "email": "a@example.com",
            "tenant_id": "t1",
            "role": "agent",
            "iat": now,
            "exp": now + dt.timedelta(minutes=5),
        },
        get_settings().jwt_secret,
        algorithm=ALGORITHM,
    )


def test_token_from_a_slightly_fast_clock_is_accepted():
    # Regression: a 1 s skew between issuer and verifier used to fail with
    # "The token is not yet valid (iat)".
    assert verify_jwt(_token_issued_at(+5))["sub"] == "u1"


def test_token_from_a_badly_wrong_clock_is_still_rejected():
    with pytest.raises(ValueError):
        verify_jwt(_token_issued_at(+300))
