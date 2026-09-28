import { describe, expect, it } from "vitest";

import { createOAuthState, isMatchingState } from "./oauth-state";

describe("createOAuthState", () => {
  it("is long enough not to be guessable", () => {
    // 32 random bytes, base64url-encoded.
    expect(createOAuthState().length).toBeGreaterThanOrEqual(43);
  });

  it("differs every time", () => {
    const seen = new Set(Array.from({ length: 50 }, createOAuthState));
    expect(seen.size).toBe(50);
  });
});

describe("isMatchingState", () => {
  it("accepts the value we issued", () => {
    const state = createOAuthState();
    expect(isMatchingState(state, state)).toBe(true);
  });

  it("rejects a different value - the attack this exists to stop", () => {
    expect(isMatchingState(createOAuthState(), createOAuthState())).toBe(false);
  });

  it("rejects a missing cookie, so a stripped cookie is not a way in", () => {
    const state = createOAuthState();
    expect(isMatchingState(state, null)).toBe(false);
    expect(isMatchingState(state, undefined)).toBe(false);
    expect(isMatchingState(state, "")).toBe(false);
  });

  it("rejects a missing callback value", () => {
    const state = createOAuthState();
    expect(isMatchingState(null, state)).toBe(false);
    expect(isMatchingState("", state)).toBe(false);
  });

  it("rejects when both are absent, rather than treating empty as equal", () => {
    expect(isMatchingState(null, null)).toBe(false);
    expect(isMatchingState("", "")).toBe(false);
  });

  it("rejects a prefix of the real value", () => {
    const state = createOAuthState();
    expect(isMatchingState(state.slice(0, -1), state)).toBe(false);
    expect(isMatchingState(state + "x", state)).toBe(false);
  });
});
