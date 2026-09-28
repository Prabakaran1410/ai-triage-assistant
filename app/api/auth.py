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
    state: str | None = Query(
        None,
        description="Opaque CSRF value from the caller; echoed back by the IdP.",
    ),
):
    """Redirect to the customer's own IdP login page via WorkOS.

    On `state`: CSRF protection for an OAuth round-trip works by binding the
    state to the *browser* that began the flow, normally through a cookie.
    This API never sees that browser - WorkOS returns to the console, which
    then exchanges the code here server to server. So the console generates
    the state, stores it in its own first-party cookie and verifies it on
    the way back; this endpoint only forwards it to WorkOS.

    A caller that does not supply one (the direct-to-API flow used before
    the console existed, and in testing) still gets a random value, so the
    parameter is always present in the authorization request - but nothing
    verifies it in that case, because nothing can.
    """
    settings = get_settings()
    redirect_uri = settings.sso_redirect_uri or f"{settings.app_base_url}/auth/callback"
    url = get_authorization_url(
        organization_id, redirect_uri, state or secrets.token_urlsafe(16)
    )
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
