"""WorkOS SSO + our own session JWT.

WorkOS authenticates *who* someone is against a customer's own identity
provider (Okta, Azure AD, Google Workspace, ...). It never manages our
tenant/user data. A successful SSO login is exchanged here for our own
short-lived, signed JWT - every other endpoint verifies that JWT
(app/core/security.py) and never talks to WorkOS directly.

Tenant mapping: each customer has one WorkOS Organization (holding their SSO
connection), mapped to one row in our own `tenants` table via
tenants.workos_organization_id (db/migrations/0005). A login can only ever
resolve to a tenant that's been explicitly mapped - an Organization with no
matching tenant is refused, not silently allowed through.
"""
import datetime as dt
import uuid

import jwt
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine, tenant_scoped_connection

ALGORITHM = "HS256"


def _client():
    import workos

    settings = get_settings()
    if not settings.workos_api_key or not settings.workos_client_id:
        raise RuntimeError("WORKOS_API_KEY / WORKOS_CLIENT_ID is not set")
    return workos.WorkOSClient(
        api_key=settings.workos_api_key, client_id=settings.workos_client_id
    )


def get_authorization_url(organization_id: str, redirect_uri: str, state: str) -> str:
    return _client().sso.get_authorization_url(
        organization_id=organization_id,
        redirect_uri=redirect_uri,
        state=state,
    )


async def _resolve_tenant_id(organization_id: str) -> str:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("select id from tenants where workos_organization_id = :org_id"),
                {"org_id": organization_id},
            )
        ).fetchone()
    if row is None:
        raise ValueError(
            f"WorkOS organization {organization_id!r} is not mapped to any tenant"
        )
    return str(row.id)


async def _upsert_user(tenant_id: str, email: str) -> tuple[str, str]:
    """Returns (user_id, role). New users default to the least-privileged
    role - promotion to reviewer/admin is a deliberate action elsewhere, not
    something a first login grants."""
    async with tenant_scoped_connection(tenant_id) as conn:
        existing = (
            await conn.execute(
                text(
                    "select id, role from users where tenant_id = :tenant_id and email = :email"
                ),
                {"tenant_id": tenant_id, "email": email},
            )
        ).fetchone()
        if existing is not None:
            return str(existing.id), existing.role

        user_id = str(uuid.uuid4())
        await conn.execute(
            text(
                "insert into users (id, tenant_id, email, role) "
                "values (:id, :tenant_id, :email, 'agent')"
            ),
            {"id": user_id, "tenant_id": tenant_id, "email": email},
        )
        return user_id, "agent"


def issue_jwt(*, user_id: str, email: str, tenant_id: str, role: str) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


async def handle_sso_callback(code: str) -> str:
    """Exchange a WorkOS authorization code for our own JWT."""
    result = _client().sso.get_profile_and_token(code)
    profile = result.profile

    if not profile.organization_id:
        raise ValueError("SSO profile has no organization_id - cannot map to a tenant")

    tenant_id = await _resolve_tenant_id(profile.organization_id)
    user_id, role = await _upsert_user(tenant_id, profile.email)
    return issue_jwt(user_id=user_id, email=profile.email, tenant_id=tenant_id, role=role)


def verify_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        raise ValueError(f"invalid or expired token: {e}") from e
