import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { startSession, useSessionStore } from "@/lib/session";
import {
  ESCALATED_RUN,
  FAILED_RUN,
  RESOLVED_RUN,
  TEST_DISPUTE_ID,
  TEST_TOKEN,
} from "@/test/fixtures";
import { mediationBackend } from "@/test/msw/mediation";
import { renderApp } from "@/test/render";

import { createMediationClient, type MediationClient, NOT_STARTED_MESSAGE } from "./client";
import { CLOSE_INVALID_TOKEN } from "./events";
import { useMediationStore } from "./store";

const signIn = () => startSession({ access_token: TEST_TOKEN, expires_in: 1800 });

const clients: MediationClient[] = [];

/** A client of its own with short timeouts, connected and ready. */
async function connectedClient(options: Parameters<typeof createMediationClient>[0] = {}) {
  signIn();
  const client = createMediationClient(options);
  clients.push(client);
  client.connect();
  await waitFor(() => expect(useMediationStore.getState().connection.state).toBe("open"));
  return client;
}

const run = () => useMediationStore.getState().runs[TEST_DISPUTE_ID];

afterEach(() => {
  clients.splice(0).forEach((client) => client.disconnect());
});

describe("the live connection in the app", () => {
  it("connects once signed in and shows it in the header", async () => {
    signIn();
    renderApp("/cases");

    expect(await screen.findByRole("status")).toHaveTextContent("Live");
  });

  it("offers to retry at once after the server drops the connection", async () => {
    signIn();
    const { user } = renderApp("/cases");
    await screen.findByText("Live");

    mediationBackend.dropAll();
    await user.click(await screen.findByRole("button", { name: "Retry now" }));

    expect(await screen.findByText("Live")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry now" })).not.toBeInTheDocument();
  });

  it("ends the session when the server refuses the token", async () => {
    signIn();
    mediationBackend.refuseWith(CLOSE_INVALID_TOKEN);
    renderApp("/cases");

    expect(await screen.findByText("Your session expired")).toBeInTheDocument();
    expect(useSessionStore.getState().session).toBeNull();
  });

  it("forgets every run on sign-out", async () => {
    signIn();
    const { user } = renderApp("/cases");
    await screen.findByText("Live");
    mediationBackend.broadcast(...RESOLVED_RUN);
    await waitFor(() => expect(run()?.status).toBe("resolved"));

    await user.click(screen.getByRole("button", { name: /ada@seller\.test/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(useMediationStore.getState().runs).toEqual({});
    expect(useMediationStore.getState().connection.state).toBe("idle");
  });
});

describe("mediating", () => {
  it("streams a run from the request to the escalation", async () => {
    mediationBackend.onMessage((message, reply) => {
      if (message.event === "seller.mediate") reply(...ESCALATED_RUN);
    });
    const client = await connectedClient();

    expect(client.mediate(TEST_DISPUTE_ID)).toEqual({ ok: true });

    await waitFor(() => expect(run()?.explanation).not.toBeNull());
    expect(run()).toMatchObject({ status: "escalated", startedHere: true });
    expect(mediationBackend.received).toEqual([
      { event: "seller.mediate", data: { dispute_id: TEST_DISPUTE_ID } },
    ]);
  });

  it("refuses a second run of a dispute while one is under way, but not of another", async () => {
    mediationBackend.onMessage((message, reply) => {
      if (message.event === "seller.mediate") reply(...RESOLVED_RUN.slice(0, 4));
    });
    const client = await connectedClient();

    client.mediate(TEST_DISPUTE_ID);
    await waitFor(() => expect(run()?.status).toBe("reasoning"));

    expect(client.mediate(TEST_DISPUTE_ID)).toEqual({ ok: false, reason: "running" });
    expect(client.mediate("FIXTURE-NAD-001")).toEqual({ ok: true });

    client.disconnect();
    expect(client.mediate("FIXTURE-UNAUTH-001")).toEqual({ ok: false, reason: "offline" });
  });

  it("fails a run the server never starts", async () => {
    const client = await connectedClient({ startTimeoutMs: 50 });

    client.mediate(TEST_DISPUTE_ID);

    await waitFor(() => expect(run()?.status).toBe("failed"));
    expect(run()?.error).toBe(NOT_STARTED_MESSAGE);
  });

  it("ends a run when the server reports an error, and allows another", async () => {
    mediationBackend.onMessage((message, reply) => {
      if (message.event === "seller.mediate") reply(...FAILED_RUN);
    });
    const client = await connectedClient();

    client.mediate(TEST_DISPUTE_ID);

    await waitFor(() => expect(run()?.status).toBe("failed"));
    expect(run()?.error).toBe("Unable to locate credentials");
    expect(client.mediate(TEST_DISPUTE_ID)).toEqual({ ok: true });
  });
});

describe("keeping server data fresh", () => {
  it("asks for a refetch when a run ends, when another client acts, and after an outage", async () => {
    const client = await connectedClient();
    const settled = vi.fn();
    client.onSettled(settled);

    mediationBackend.broadcast(...ESCALATED_RUN.slice(0, -1));
    await waitFor(() => expect(run()?.status).toBe("escalated"));
    expect(settled).not.toHaveBeenCalled();

    mediationBackend.broadcast(...ESCALATED_RUN.slice(-1));
    await waitFor(() => expect(settled).toHaveBeenCalledTimes(1));

    // Another client approved it over the socket: no run here owns the event.
    mediationBackend.broadcast([
      "case.executed",
      { dispute_id: TEST_DISPUTE_ID, result: { executed: true, action_taken: "Refunded" } },
    ]);
    await waitFor(() => expect(settled).toHaveBeenCalledTimes(2));

    mediationBackend.dropAll();
    await waitFor(() => expect(useMediationStore.getState().connection.state).toBe("reconnecting"));
    client.retryNow();
    await waitFor(() => expect(settled).toHaveBeenCalledTimes(3));
  });
});
