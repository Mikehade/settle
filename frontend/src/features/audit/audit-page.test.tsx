import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { AuditEntry } from "@/lib/api/types";
import { startSession } from "@/lib/session";
import { auditEntry, ESCALATED_REFUND, errorEnvelope, TEST_TOKEN } from "@/test/fixtures";
import { auditHandlers } from "@/test/msw/audit";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const signIn = () => startSession({ access_token: TEST_TOKEN, expires_in: 1800 });

/** Newest first, as the backend lists them: one of each way a decision can end. */
const ENTRIES: AuditEntry[] = [
  auditEntry({
    id: "entry-approved",
    paypal_dispute_id: "PP-D-2001",
    decision: { ...ESCALATED_REFUND, gate: "execute" },
    outcome: "refund",
    confidence: 0.62,
    gate: "execute",
    executed: true,
    engine: "approved",
    action_taken: "Issued refund of 59.99 USD",
    paypal_result: { id: "REFUND-1", status: "COMPLETED" },
    created_at: "2026-11-08T10:00:00",
  }),
  auditEntry({
    id: "entry-escalated",
    paypal_dispute_id: "PP-D-2001",
    decision: { ...ESCALATED_REFUND },
    outcome: "refund",
    confidence: 0.62,
    created_at: "2026-11-08T09:00:00",
  }),
  auditEntry({
    id: "entry-dry-run",
    paypal_dispute_id: "FIXTURE-NAD-001",
    decision: {
      outcome: "reship",
      confidence: 0.9,
      rationale: "The shirt arrived in the wrong size, so a replacement puts it right.",
      classification: "not_as_described",
      evidence_summary: "Delivered in size M instead of L.",
      gate: "execute",
      gate_reason: "Within guardrails.",
    },
    outcome: "reship",
    confidence: 0.9,
    gate: "execute",
    action_taken: "Offered a replacement to the buyer (dry run, no live capture)",
    paypal_result: { dry_run: true, would_offer: "REFUND_WITH_REPLACEMENT" },
    served_by: "test-model",
    created_at: "2026-11-07T09:00:00",
  }),
  auditEntry({
    id: "entry-failed",
    paypal_dispute_id: "PP-D-2002",
    outcome: "accept",
    confidence: 0.85,
    action_taken: "Execution failed, escalated",
    paypal_result: { error: "PayPal said no" },
    created_at: "2026-11-06T09:00:00",
  }),
];

/** The table's rows, without its header. */
const rows = () => screen.getAllByRole("row").slice(1);
const rowFor = (id: string) => {
  const row = rows().find((item) => within(item).queryByText(id));
  if (!row) throw new Error(`No row for ${id}`);
  return row;
};

describe("the audit trail", () => {
  it("lists each decision with what came of it", async () => {
    server.use(...auditHandlers(ENTRIES));
    signIn();
    renderApp("/audit");

    expect(await screen.findByText("4 decisions")).toBeInTheDocument();
    const [approved, escalated, dryRun, failed] = rows();

    expect(approved).toHaveTextContent("Carried out");
    expect(approved).toHaveTextContent("Approved by you · Issued refund of 59.99 USD");
    expect(approved).toHaveTextContent("Refund");
    expect(approved).toHaveTextContent("62% confident");

    expect(escalated).toHaveTextContent("Sent to you");
    expect(escalated).toHaveTextContent("Nothing sent to PayPal");

    expect(dryRun).toHaveTextContent("Dry run");
    expect(dryRun).toHaveTextContent("Demo");
    expect(within(dryRun!).getByText("Offered a replacement to the buyer")).toBeInTheDocument();

    expect(failed).toHaveTextContent("Couldn't carry out");
    expect(failed).toHaveTextContent("Accept claim");
  });

  it("says so when nothing has been decided yet", async () => {
    signIn();
    renderApp("/audit");

    expect(await screen.findByText("No decisions yet")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("filters by result and decision, keeping both in the address bar", async () => {
    server.use(...auditHandlers(ENTRIES));
    signIn();
    const { user, router } = renderApp("/audit");

    await user.click(await screen.findByRole("tab", { name: "Sent to you" }));
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(rowFor("PP-D-2002")).toHaveTextContent("Couldn't carry out");

    await user.click(screen.getByRole("button", { name: "Decision: Any decision" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Refund" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rowFor("PP-D-2001")).toHaveTextContent("Sent to you");
    expect(router.state.location.search).toEqual({ gate: "escalate", outcome: "refund" });

    await user.click(screen.getByRole("tab", { name: "Carried out" }));
    await user.click(screen.getByRole("button", { name: "Decision: Refund" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Accept claim" }));
    expect(await screen.findByText("No decisions match these filters.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(rows()).toHaveLength(4));
    expect(router.state.location.search).toEqual({});
  });

  it("pages through a long trail", async () => {
    const many = Array.from({ length: 30 }, (_, index) =>
      auditEntry({ paypal_dispute_id: `PP-D-${String(3000 + index)}` }),
    );
    server.use(...auditHandlers(many));
    signIn();
    const { user, router } = renderApp("/audit");

    expect(await screen.findByText("1 to 25 of 30 decisions")).toBeInTheDocument();
    expect(rows()).toHaveLength(25);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("26 to 30 of 30 decisions")).toBeInTheDocument();
    expect(rows()).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(router.state.location.search).toEqual({ page: 2 });
  });

  it("opens a decision's full record beside the list", async () => {
    server.use(...auditHandlers(ENTRIES));
    signIn();
    const { user, router } = renderApp("/audit");

    await user.click(
      within(await waitFor(() => rowFor("FIXTURE-NAD-001"))).getByRole("link", {
        name: /FIXTURE-NAD-001/,
      }),
    );

    const sheet = await screen.findByRole("dialog", { name: "Decision on FIXTURE-NAD-001" });
    expect(router.state.location.search).toEqual({ entry: "entry-dry-run" });
    expect(within(sheet).getByText("Demo")).toBeInTheDocument();

    const decided = await within(sheet).findByRole("region", { name: "How Settle decided" });
    expect(within(decided).getByText("Dry run")).toBeInTheDocument();
    expect(decided).toHaveTextContent("Delivered in size M instead of L.");
    expect(decided).toHaveTextContent("90% confident");
    expect(within(sheet).getByRole("region", { name: "What Settle saw" })).toHaveTextContent(
      "Wireless earbuds",
    );
    const record = within(sheet).getByRole("region", { name: "Record" });
    expect(record).toHaveTextContent("Mediator");
    expect(record).toHaveTextContent("test-model");
    expect(record).toHaveTextContent("REFUND_WITH_REPLACEMENT");
    expect(within(sheet).getByRole("link", { name: "Open case" })).toHaveAttribute(
      "href",
      "/cases/FIXTURE-NAD-001",
    );

    await user.click(within(sheet).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.search).toEqual({});
  });

  it("opens the entry a link points at", async () => {
    server.use(...auditHandlers(ENTRIES));
    signIn();
    renderApp("/audit?entry=entry-approved");

    const sheet = await screen.findByRole("dialog", { name: "Decision on PP-D-2001" });
    expect(within(sheet).getByText("Approved by you")).toBeInTheDocument();
    expect(await within(sheet).findByText("Your approval")).toBeInTheDocument();
  });

  it("offers to try again when the trail doesn't load", async () => {
    server.use(
      http.get(
        "*/api/v1/audit",
        () =>
          HttpResponse.json(errorEnvelope("COMMON_INTERNAL_ERROR", "Something went wrong"), {
            status: 500,
          }),
        { once: true },
      ),
    );
    signIn();
    const { user } = renderApp("/audit");

    expect(await screen.findByText("Couldn't load the audit trail")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No decisions yet")).toBeInTheDocument();
  });
});
