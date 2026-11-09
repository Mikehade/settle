import { describe, expect, it } from "vitest";

import { endSession, getActiveSession, startSession, useSessionStore } from "./session";

describe("session", () => {
  it("starts with an expiry taken from the token's lifetime", () => {
    const session = startSession({ access_token: "abc", expires_in: 1800 }, 1_000);

    expect(session).toEqual({ accessToken: "abc", expiresAt: 1_801_000 });
    expect(getActiveSession(1_000)).toEqual(session);
  });

  it("persists only the session, not why the last one ended", () => {
    startSession({ access_token: "abc", expires_in: 60 }, 0);

    expect(JSON.parse(localStorage.getItem("settle-session") ?? "{}")).toEqual({
      state: { session: { accessToken: "abc", expiresAt: 60_000 } },
      version: 0,
    });
  });

  it("ends an expired session when it is read, and says why", () => {
    startSession({ access_token: "abc", expires_in: 60 }, 0);

    expect(getActiveSession(60_000)).toBeNull();
    expect(useSessionStore.getState()).toMatchObject({ session: null, endReason: "expired" });
  });

  it("does not record a reason when there was no session to end", () => {
    endSession("signed-out");

    expect(useSessionStore.getState().endReason).toBeNull();
  });
});
