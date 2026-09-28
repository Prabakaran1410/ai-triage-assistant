import { NextResponse } from "next/server";

import { createOAuthState, OAUTH_STATE_COOKIE } from "@/lib/oauth-state";

/** A login should be completed promptly; anything older is stale, not slow. */
const STATE_MAX_AGE_SECONDS = 10 * 60;

/**
 * Begin SSO. The API builds the WorkOS authorization URL because it holds
 * the WorkOS credentials; we supply the CSRF state, because only this app
 * has a cookie on the browser to check it against later.
 */
export async function GET(request: Request) {
  const organizationId = new URL(request.url).searchParams.get("organization_id");
  if (!organizationId) {
    return NextResponse.redirect(new URL("/login?error=missing_organization", request.url));
  }

  const apiBaseUrl = process.env.API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API_BASE_URL is not set");
  }

  const state = createOAuthState();

  const target = new URL(`${apiBaseUrl}/auth/login`);
  target.searchParams.set("organization_id", organizationId);
  target.searchParams.set("state", state);

  const response = NextResponse.redirect(target.toString());
  response.cookies.set(OAUTH_STATE_COOKIE, state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    // Must be Lax, not Strict: the IdP returns the browser here by
    // top-level navigation from another site, and Strict would withhold the
    // cookie on exactly that request, breaking every login.
    sameSite: "lax",
    path: "/",
    maxAge: STATE_MAX_AGE_SECONDS,
  });
  return response;
}
