"""FastAPI dependency that turns a bearer JWT into a verified, tenant-scoped
identity. Every protected route depends on this rather than trusting a
client-supplied tenant_id in the request body - that's the whole point:
tenant identity comes from something we signed, not from what the caller
claims.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import verify_jwt

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: str
    email: str
    tenant_id: str
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = verify_jwt(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(e), headers={"WWW-Authenticate": "Bearer"}
        ) from e

    return CurrentUser(
        user_id=claims["sub"],
        email=claims["email"],
        tenant_id=claims["tenant_id"],
        role=claims["role"],
    )


# Roles, most privileged first. `admin` and `reviewer` may act on a queued
# reply; `agent` may look but not decide. Enforced server-side: the console
# also hides the buttons, but hiding a button is not access control.
ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_AGENT = "agent"
REVIEWER_ROLES = frozenset({ROLE_ADMIN, ROLE_REVIEWER})


def require_reviewer(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if current_user.role not in REVIEWER_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"role '{current_user.role}' cannot review replies",
        )
    return current_user


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Managing the knowledge base is an admin action, not a reviewer one:
    it changes what every future reply is grounded in, for everyone."""
    if current_user.role != ROLE_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"role '{current_user.role}' cannot manage the knowledge base",
        )
    return current_user
