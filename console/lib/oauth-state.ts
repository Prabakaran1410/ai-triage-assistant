import { randomBytes, timingSafeEqual } from "node:crypto";

/**
 * CSRF protection for the SSO round-trip.
 *
 * Without it, an attacker can start a login, capture their own authorization
 * code, and hand a victim a crafted callback URL. The victim's browser
 * completes the exchange and they end up silently signed in as the attacker
 * - inside a console showing another company's customer messages. The fix is
 * to prove the callback belongs to the same browser that began the flow,
 * which means a value held in a cookie on that browser and compared on the
 * way back.
 *
 * This lives in the console rather than the API because the API never sees
 * the browser: WorkOS redirects here, and the code is exchanged server to
 * server afterwards.
 */
export const OAUTH_STATE_COOKIE = "triage_oauth_state";

/** Long enough that guessing is hopeless; it only has to survive one login. */
export function createOAuthState(): string {
  return randomBytes(32).toString("base64url");
}

/**
 * Compare in constant time. A plain `===` leaks how many leading characters
 * matched through its timing, which over many attempts narrows the search.
 * The cost of avoiding that is one function call.
 */
export function isMatchingState(
  fromCallback: string | null | undefined,
  fromCookie: string | null | undefined,
): boolean {
  if (!fromCallback || !fromCookie) return false;

  const a = Buffer.from(fromCallback, "utf8");
  const b = Buffer.from(fromCookie, "utf8");
  // timingSafeEqual throws on length mismatch, which would itself leak the
  // length, so compare lengths separately and still run the comparison.
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}
