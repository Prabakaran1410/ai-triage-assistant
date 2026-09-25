import logging
import secrets

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.services.auth import get_authorization_url, handle_sso_callback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(
    organization_id: str = Query(
        ..., description="The WorkOS Organization ID for the tenant logging in"
    ),
):
    """Redirects to the customer's own IdP login page via WorkOS.

    Phase 0 note: `state` isn't yet persisted and checked on callback (no
    CSRF protection on the redirect round-trip). Fine for the current
    single-environment testing setup; tracked as a follow-up before this
    handles real customer logins.
    """
    settings = get_settings()
    redirect_uri = f"{settings.app_base_url}/auth/callback"
    state = secrets.token_urlsafe(16)
    url = get_authorization_url(organization_id, redirect_uri, state)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    # On a failed login WorkOS redirects back with error/error_description and
    # no `code`. Surface that as a clear 400 instead of a 422 about a missing
    # field, which hides the real reason.
    if error or not code:
        raise HTTPException(
            400, f"SSO login failed: {error_description or error or 'no authorization code'}"
        )
    try:
        token = await handle_sso_callback(code)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        # WorkOS rejected the code, a DB error, etc. Log the real cause so it
        # is visible in Render's logs, and tell the caller it was the SSO
        # exchange that failed rather than returning an opaque 500.
        logger.exception("SSO callback failed")
        raise HTTPException(502, "SSO login could not be completed") from e
    return {"access_token": token, "token_type": "bearer"}
