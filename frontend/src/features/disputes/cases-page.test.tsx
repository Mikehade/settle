import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { startSession } from "@/lib/session";
import {
  disputeRecord,
  envelope,
  errorEnvelope,
  openDispute,
  RESOLVED_RUN,
  TEST_DISPUTE_ID,
  TEST_TOKEN,
} from "@/test/fixtures";
import { disputeHandlers } from "@/test/msw/disputes";
import { mediationBackend } from "@/test/msw/mediation";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const signIn = () => startSession({ access_token: TEST_TOKEN, expires_in: 1800 });

const DEMO_OPEN = [
  openDispute("FIXTURE-NR-001"),
  openDispute("FIXTURE-NAD-001", { reason: "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED" }),
  openDispute("FIXTURE-UNAUTH-001", { reason: "UNAUTHORISED" }),
];

const RECORDS = [
  disputeRecord({
    paypal_dispute_id: "FIXTURE-NAD-001",
    status: "resolved",
    dispute_type: "not_as_described",
    disputed_amount: 32,
    outcome: "refund",
    refund_amount: 20,
    buyer_complaint: "The shirt arrived in the wrong size.",
  }),
  disputeRecord(),
];

/** Each row's dispute id and status, top to bottom. */
async function rows() {
  const table = await screen.findByRole("table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.textContent);
}

describe("the cases list", () => {
  it("lists every case with what needs the seller first, and counts those in the sidebar", async () => {
    server.use(...disputeHandlers({ open: DEMO_OPEN, records: RECORDS }));
    signIn();
    renderApp("/cases");

    await waitFor(async () => expect(await rows()).toHaveLength(3));
    const [first, second, third] = await rows();
    expect(first).toMatch(/FIXTURE-NR-001.*Not received.*Needs you.*\$59\.99/);
    expect(second).toMatch(/FIXTURE-UNAUTH-001.*Unauthorized or other.*Open/);
    expect(third).toMatch(/FIXTURE-NAD-001.*Resolved.*\$32\.00.*Refund \$20\.00/);

    expect(screen.getByRole("link", { name: "Cases, 1 waiting on you" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Needs you 1" })).toBeInTheDocument();
  });

  it("filters by status and by search, keeping both in the address", async () => {
    server.use(...disputeHandlers({ open: DEMO_OPEN, records: RECORDS }));
    signIn();
    const { user, router } = renderApp("/cases");
    await waitFor(async () => expect(await rows()).toHaveLength(3));

    await user.click(screen.getByRole("tab", { name: /Needs you/ }));
    expect(await rows()).toEqual([expect.stringContaining("FIXTURE-NR-001")]);
    expect(router.state.location.search).toEqual({ filter: "needs_you" });

    await user.click(screen.getByRole("tab", { name: /All/ }));
    await user.type(screen.getByRole("searchbox", { name: "Search cases" }), "wrong size");
    await waitFor(async () =>
      expect(await rows()).toEqual([expect.stringContaining("FIXTURE-NAD-001")]),
    );
    expect(router.state.location.search).toEqual({ q: "wrong size" });

    await user.type(screen.getByRole("searchbox", { name: "Search cases" }), " nothing");
    expect(await screen.findByText("No cases match “wrong size nothing”.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));

    await waitFor(async () => expect(await rows()).toHaveLength(3));
    expect(screen.getByRole("searchbox", { name: "Search cases" })).toHaveValue("");
    expect(router.state.location.search).toEqual({});
  });

  it("starts from the filter and search in the address", async () => {
    server.use(...disputeHandlers({ open: DEMO_OPEN, records: RECORDS }));
    signIn();
    renderApp("/cases?filter=open&q=unauth");

    await waitFor(async () =>
      expect(await rows()).toEqual([expect.stringContaining("FIXTURE-UNAUTH-001")]),
    );
    expect(screen.getByRole("tab", { name: /Open/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("searchbox", { name: "Search cases" })).toHaveValue("unauth");
  });

  it("opens a case from its row", async () => {
    server.use(...disputeHandlers({ open: DEMO_OPEN, records: RECORDS }));
    signIn();
    const { user } = renderApp("/cases");

    await user.click(await screen.findByRole("link", { name: "FIXTURE-UNAUTH-001" }));

    expect(await screen.findByRole("heading", { name: "FIXTURE-UNAUTH-001" })).toBeInTheDocument();
  });

  it("shows a mediation in its row as it happens, and refreshes the lists when it settles", async () => {
    server.use(...disputeHandlers({ open: DEMO_OPEN }));
    signIn();
    renderApp("/cases");
    await screen.findByText("Live");
    await waitFor(async () => expect(await rows()).toHaveLength(3));

    mediationBackend.broadcast(...RESOLVED_RUN.slice(0, 5));
    await waitFor(async () => expect((await rows())[0]).toMatch(/FIXTURE-NR-001.*Mediating/));

    // The backend records the result before it says the run is over.
    server.use(
      ...disputeHandlers({
        open: DEMO_OPEN,
        records: [disputeRecord({ status: "resolved", outcome: "refund", refund_amount: 59.99 })],
      }),
    );
    mediationBackend.broadcast(...RESOLVED_RUN.slice(5));

    await waitFor(async () =>
      expect((await rows()).at(-1)).toMatch(/FIXTURE-NR-001.*Resolved.*\$59\.99.*Refund \$59\.99/),
    );
    expect(screen.getByRole("tab", { name: "Closed 1" })).toBeInTheDocument();
  });
});

describe("when the lists don't load", () => {
  const unavailable = (path: string) =>
    http.get(path, () =>
      HttpResponse.json(errorEnvelope("COMMON_SERVICE_UNAVAILABLE", "PayPal is unavailable"), {
        status: 503,
      }),
    );

  it("keeps what did load, and retries the rest", async () => {
    // The first handler for a path wins.
    server.use(unavailable("*/api/v1/disputes/open"), ...disputeHandlers({ records: RECORDS }));
    signIn();
    const { user } = renderApp("/cases");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load open disputes from PayPal");
    expect(alert).toHaveTextContent("Showing the cases Settle has already handled.");
    expect(await rows()).toHaveLength(2);

    server.use(http.get("*/api/v1/disputes/open", () => HttpResponse.json(envelope(DEMO_OPEN))));
    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    await waitFor(async () => expect(await rows()).toHaveLength(3));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says so, rather than claiming there are no disputes, when nothing loads", async () => {
    server.use(unavailable("*/api/v1/disputes/open"), unavailable("*/api/v1/disputes"));
    signIn();
    renderApp("/cases");

    expect(await screen.findAllByRole("alert")).toHaveLength(2);
    expect(screen.queryByText("No disputes yet")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("explains an empty list when there is genuinely nothing", async () => {
    signIn();
    renderApp("/cases");

    expect(await screen.findByText("No disputes yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /waiting on you/ })).not.toBeInTheDocument();
  });
});

it("shows the demo case id as the case page's title", async () => {
  signIn();
  renderApp(`/cases/${TEST_DISPUTE_ID}`);

  expect(await screen.findByRole("heading", { name: TEST_DISPUTE_ID })).toBeInTheDocument();
});
