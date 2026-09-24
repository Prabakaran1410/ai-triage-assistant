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
