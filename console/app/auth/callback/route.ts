import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { isMatchingState, OAUTH_STATE_COOKIE } from "@/lib/oauth-state";
import { setSessionToken } from "@/lib/session";

/**
 * Where WorkOS sends the browser after a successful login.
 *
 * The authorization code is exchanged here, server to server, by calling the
 * API (which holds the WorkOS API key and maps the organization to a
 * tenant). The resulting JWT goes straight into an httpOnly cookie, so it
 * never appears in a URL, a page body, or anywhere browser JavaScript can
 * reach it.
 */
const SESSION_MAX_AGE_SECONDS = 60 * 60;

function failed(request: Request, reason: string) {
  return NextResponse.redirect(
    new URL(`/login?error=${encodeURIComponent(reason)}`, request.url),
  );
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;

  const error = params.get("error_description") ?? params.get("error");
  if (error) return failed(request, error);

  // Check CSRF state before anything else, and before spending the code:
  // this request may not have come from a login we started.
  const cookieStore = await cookies();
  const expectedState = cookieStore.get(OAUTH_STATE_COOKIE)?.value;
  const presentedState = params.get("state");
  if (!isMatchingState(presentedState, expectedState)) {
    return failed(
      request,
      "This sign-in link did not come from a login started in this browser. Please sign in again.",
    );
  }
  // One state, one login. Clearing it here stops the same callback URL being
  // replayed even within the cookie's lifetime.
  cookieStore.delete(OAUTH_STATE_COOKIE);

  const code = params.get("code");
  if (!code) return failed(request, "missing_code");

  const apiBaseUrl = process.env.API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API_BASE_URL is not set");
  }

  const response = await fetch(
    `${apiBaseUrl}/auth/callback?code=${encodeURIComponent(code)}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      /* not JSON; use the raw body */
    }
    return failed(request, detail);
  }

  const { access_token: accessToken } = (await response.json()) as {
    access_token: string;
  };
  await setSessionToken(accessToken, SESSION_MAX_AGE_SECONDS);

  return NextResponse.redirect(new URL("/queue", request.url));
}
