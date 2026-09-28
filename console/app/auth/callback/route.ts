import { NextResponse } from "next/server";

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

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const error = params.get("error_description") ?? params.get("error");
  if (error) {
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(error)}`, request.url),
    );
  }

  const code = params.get("code");
  if (!code) {
    return NextResponse.redirect(new URL("/login?error=missing_code", request.url));
  }

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
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(detail)}`, request.url),
    );
  }

  const { access_token: accessToken } = (await response.json()) as {
    access_token: string;
  };
  await setSessionToken(accessToken, SESSION_MAX_AGE_SECONDS);

  return NextResponse.redirect(new URL("/queue", request.url));
}
