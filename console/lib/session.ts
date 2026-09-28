import { cookies } from "next/headers";

// The JWT our API issued. It lives in a first-party httpOnly cookie on the
// console's own origin, so browser JavaScript can never read it, and it is
// never sent to the browser in a URL or a page body. The API sits on a
// different origin (Render vs Vercel), and a cookie set *by* the API would
// be third-party to this app - increasingly blocked by browsers. This is
// why the console is a backend-for-frontend rather than a direct caller.
const SESSION_COOKIE = "triage_session";

export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

export async function setSessionToken(token: string, maxAgeSeconds: number) {
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    // Vercel serves over HTTPS; locally `next dev` is HTTP, so this would
    // stop the cookie being stored there.
    secure: process.env.NODE_ENV === "production",
    // Lax, not None: the console and the API never share a browser request,
    // so there is no cross-site POST to accommodate, and Lax is the safer
    // default against CSRF.
    sameSite: "lax",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

export async function clearSessionToken() {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

export type SessionUser = { email: string; role: string; tenantId: string };

/** Read the claims without verifying: the API verifies on every call, and
 *  this is only used to render a name and hide buttons. Anything that
 *  matters is decided server-side by the API, not here. */
export function readClaims(token: string): SessionUser | null {
  try {
    const payload = token.split(".")[1];
    const json = JSON.parse(
      Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"),
    );
    return { email: json.email, role: json.role, tenantId: json.tenant_id };
  } catch {
    return null;
  }
}
