import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { startSession } from "@/lib/session";
import {
  auditEntry,
  disputeRecord,
  envelope,
  errorEnvelope,
  ESCALATED_REFUND,
  ESCALATED_RUN,
  FAILED_RUN,
  TEST_DISPUTE_ID,
  TEST_TOKEN,
} from "@/test/fixtures";
import { disputeHandlers } from "@/test/msw/disputes";
import { mediationBackend } from "@/test/msw/mediation";
import { server } from "@/test/msw/server";
import { renderApp } from "@/test/render";

const signIn = () => startSession({ access_token: TEST_TOKEN, expires_in: 1800 });
const CASE_PATH = `/cases/${TEST_DISPUTE_ID}`;
const APPROVE = `*/api/v1/disputes/${TEST_DISPUTE_ID}/approve`;
const REJECT = `*/api/v1/disputes/${TEST_DISPUTE_ID}/reject`;

const escalated = { records: [disputeRecord()], trails: { [TEST_DISPUTE_ID]: [auditEntry()] } };

/** Serves the escalated demo case, and what it becomes once `action` succeeds. */
function serveReview(action: "approve" | "reject", after: { status: string }) {
  const calls: string[] = [];
  server.use(
    http.post(action === "approve" ? APPROVE : REJECT, () => {
      calls.push(action);
      server.use(
        ...disputeHandlers({
          ...escalated,
          records: [disputeRecord({ ...after, resolved_at: "2026-11-07T12:00:00" })],
        }),
      );
      return HttpResponse.json(
        envelope({
          dispute_id: TEST_DISPUTE_ID,
          executed: false,
          action_taken: action === "approve" ? "Acknowledged" : "Recommendation rejected",
        }),
      );
    }),
    ...disputeHandlers(escalated),
  );
  return calls;
}

describe("the case page", () => {
  it("shows an escalated case: the recommendation, the reasoning and the case file", async () => {
    server.use(...disputeHandlers(escalated));
    signIn();
    renderApp(CASE_PATH);

    expect(await screen.findByRole("heading", { name: TEST_DISPUTE_ID })).toBeInTheDocument();
    expect(await screen.findByText("Needs you")).toBeInTheDocument();

    const decision = screen.getByRole("region", { name: "Decision" });
    expect(decision).toHaveTextContent("Escalated to you");
    expect(decision).toHaveTextContent(
      "Review this dispute manually and respond in the PayPal Resolution Center.",
    );
    expect(screen.getByRole("list", { name: "Reasoning" })).toHaveTextContent("Not received");

    expect(screen.getByText("Wireless earbuds", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Not shipped")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });

  it("shows a decision Settle carried out itself, with its history", async () => {
    server.use(
      ...disputeHandlers({
        records: [
          disputeRecord({
            status: "resolved",
            outcome: "reship",
            confidence: 0.9,
            resolved_at: "2026-11-07T21:42:24",
          }),
        ],
        trails: {
          [TEST_DISPUTE_ID]: [
            auditEntry({
              decision: {
                outcome: "reship",
                confidence: 0.9,
                rationale: "The buyer received the wrong size; the seller offered an exchange.",
                classification: "not_as_described",
                evidence_summary: "Delivered in size **M** instead of L.",
                gate: "execute",
                gate_reason: "Within guardrails.",
              },
              outcome: "reship",
              confidence: 0.9,
              gate: "execute",
              action_taken: "Offered a replacement to the buyer (dry run, no live capture)",
              paypal_result: { dry_run: true, would_offer: "REFUND_WITH_REPLACEMENT" },
            }),
          ],
        },
      }),
    );
    signIn();
    renderApp(CASE_PATH);

    const decision = await screen.findByRole("region", { name: "Decision" });
    expect(decision).toHaveTextContent("Reship");
    expect(decision).toHaveTextContent("90% confident");
    expect(decision).toHaveTextContent("Offered a replacement to the buyer");
    expect(within(decision).getByText("Dry run")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.getByText("Settle carried out its decision")).toBeInTheDocument();
    expect(screen.getByText("M").tagName).toBe("STRONG");
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("approves once confirmed, saying first what will happen", async () => {
    const calls = serveReview("approve", { status: "resolved" });
    signIn();
    const { user } = renderApp(CASE_PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("nothing is sent to PayPal");
    expect(calls).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Resolved")).toBeInTheDocument();
    expect(calls).toEqual(["approve"]);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByText(/You approved\. There was nothing for Settle/)).toBeInTheDocument();
  });

  it("names the amount before approving a refund", async () => {
    server.use(
      ...disputeHandlers({
        records: [disputeRecord()],
        trails: { [TEST_DISPUTE_ID]: [auditEntry({ decision: { ...ESCALATED_REFUND } })] },
      }),
    );
    signIn();
    const { user } = renderApp(CASE_PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "Settle will refund $59.99 to the buyer through PayPal. This is a demo dispute, so it is simulated.",
    );
    expect(within(dialog).getByRole("button", { name: "Approve and refund $59.99" })).toBeVisible();
  });

  it("rejects once confirmed", async () => {
    const calls = serveReview("reject", { status: "rejected" });
    signIn();
    const { user } = renderApp(CASE_PATH);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Reject" }),
    );

    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(calls).toEqual(["reject"]);
    expect(screen.getByText("You rejected the recommendation")).toBeInTheDocument();
  });

  it("explains a case someone already acted on", async () => {
    server.use(
      http.post(APPROVE, () =>
        HttpResponse.json(
          errorEnvelope("DISPUTE_ALREADY_RESOLVED", "This case has already been acted on."),
          { status: 409 },
        ),
      ),
      ...disputeHandlers(escalated),
    );
    signIn();
    const { user } = renderApp(CASE_PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Approve" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This case was already acted on");
    expect(alert).toHaveTextContent("This case has already been acted on.");
  });

  it("warns that an approval with no answer may still have gone through", async () => {
    server.use(
      http.post(APPROVE, () => HttpResponse.error()),
      ...disputeHandlers(escalated),
    );
    signIn();
    const { user } = renderApp(CASE_PATH);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Approve" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Settle didn't answer");
    expect(alert).toHaveTextContent("check the case's status before trying again");
  });
});

describe("mediating from the case page", () => {
  const unseen = { previews: { [TEST_DISPUTE_ID]: { item_name: "Wireless earbuds" } } };

  it("mediates a case Settle hasn't seen, streaming the run into the page", async () => {
    server.use(...disputeHandlers(unseen));
    mediationBackend.onMessage((message, reply) => {
      if (message.event !== "seller.mediate") return;
      // The backend records the escalation before it says the run is over.
      server.use(...disputeHandlers(escalated));
      reply(...ESCALATED_RUN);
    });
    signIn();
    const { user } = renderApp(CASE_PATH);
    await screen.findByText("Live");

    expect(await screen.findByText(/^Settle hasn't mediated this case yet\./)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mediate" }));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByText("Needs you")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Reasoning" })).toHaveTextContent("Weigh the evidence");
    expect(mediationBackend.received).toEqual([
      { event: "seller.mediate", data: { dispute_id: TEST_DISPUTE_ID } },
    ]);
  });

  it("shows why a run failed, and offers to mediate again", async () => {
    server.use(...disputeHandlers(unseen));
    mediationBackend.onMessage((message, reply) => {
      if (message.event === "seller.mediate") reply(...FAILED_RUN);
    });
    signIn();
    const { user } = renderApp(CASE_PATH);
    await screen.findByText("Live");

    await user.click(await screen.findByRole("button", { name: "Mediate" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The mediation stopped before a decision");
    expect(alert).toHaveTextContent("Unable to locate credentials");
    expect(screen.getByRole("button", { name: "Mediate again" })).toBeEnabled();
  });

  it("says so when there is no such case", async () => {
    signIn();
    renderApp("/cases/NOT-A-DISPUTE");

    expect(await screen.findByText("No case NOT-A-DISPUTE")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Back to cases" })).toBeInTheDocument(),
    );
  });
});
