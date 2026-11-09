import { describe, expect, it } from "vitest";

import type { ServerEvent } from "@/features/mediation/events";
import {
  applyServerEvent,
  initialMediationState,
  markDropped,
  type MediationState,
  requestRun,
} from "@/features/mediation/store";
import {
  auditEntry,
  disputeRecord,
  ESCALATED_REFUND,
  ESCALATED_RUN,
  FAILED_RUN,
  RESOLVED_RUN,
  type ScriptedEvent,
  TEST_DISPUTE_ID,
} from "@/test/fixtures";

import { buildCaseDetail } from "./case-detail";

const NOW = Date.UTC(2026, 10, 7, 12, 0, 0);
const FETCHED = NOW - 60_000;

function runAfter(events: ScriptedEvent[], state: MediationState = initialMediationState) {
  return events.reduce(
    (current, [event, data]) =>
      applyServerEvent(
        current,
        { event, data, messageId: "m", timestamp: "t" } as ServerEvent,
        NOW,
      ),
    state,
  ).runs[TEST_DISPUTE_ID];
}

const base = {
  id: TEST_DISPUTE_ID,
  record: undefined,
  recordFetchedAt: FETCHED,
  preview: undefined,
  trail: undefined,
  run: undefined,
  now: NOW,
};

describe("building a case's detail", () => {
  it("shows an escalated case's latest decision, ready for the seller's review", () => {
    const detail = buildCaseDetail({
      ...base,
      record: disputeRecord(),
      trail: [auditEntry()],
    });

    expect(detail).toMatchObject({
      status: "needs_you",
      awaitingReview: true,
      canMediate: false,
      run: null,
      caseFile: { item_name: "Wireless earbuds", tracking_status: "not_shipped" },
      latest: {
        recommendation: "Review this dispute manually and respond in the PayPal Resolution Center.",
        gateReason: "Mediator chose to escalate.",
        actionTaken: "Escalated to the seller",
        executed: false,
        dryRun: false,
      },
      history: [{ kind: "escalated", actionTaken: "Escalated to the seller" }],
    });
  });

  it("offers to mediate a case Settle hasn't seen, from its previewed case file", () => {
    const detail = buildCaseDetail({
      ...base,
      record: null,
      preview: { dispute_id: TEST_DISPUTE_ID, status: "open", case_file: { item_name: "Lamp" } },
    });

    expect(detail).toMatchObject({
      status: "open",
      canMediate: true,
      latest: null,
      history: [],
      caseFile: { item_name: "Lamp" },
    });
  });

  it("follows a run as it happens, and allows a review only once it is over", () => {
    const requested = requestRun(initialMediationState, TEST_DISPUTE_ID, NOW);
    const during = (events: ScriptedEvent[]) =>
      buildCaseDetail({
        ...base,
        record: disputeRecord({ status: "failed" }),
        run: runAfter(events, requested),
      });

    expect(during(ESCALATED_RUN.slice(0, 4))).toMatchObject({
      status: "mediating",
      live: true,
      canMediate: false,
      latest: null,
    });
    expect(during(ESCALATED_RUN.slice(0, -1))).toMatchObject({
      status: "needs_you",
      awaitingReview: false,
      latest: {
        recommendation: "Review this dispute manually and respond in the PayPal Resolution Center.",
      },
    });
    expect(during(ESCALATED_RUN)).toMatchObject({ status: "needs_you", awaitingReview: true });
  });

  it("shows what a run carried out, dry run included", () => {
    const detail = buildCaseDetail({ ...base, record: null, run: runAfter(RESOLVED_RUN) });

    expect(detail).toMatchObject({
      status: "resolved",
      latest: {
        decision: { outcome: "refund", refund_amount: 59.99 },
        actionTaken: "Refunded 59.99 USD",
        dryRun: true,
        rationale: "Tracking shows the label was created but the parcel never shipped.",
      },
    });
  });

  it("offers to mediate again after a run that failed", () => {
    const detail = buildCaseDetail({ ...base, record: disputeRecord(), run: runAfter(FAILED_RUN) });

    expect(detail).toMatchObject({ status: "unfinished", canMediate: true });
    expect(detail?.run?.error).toBe("Unable to locate credentials");
  });

  it("goes by the record once it is newer than an interrupted run", () => {
    const interrupted = markDropped({
      ...initialMediationState,
      runs: { [TEST_DISPUTE_ID]: runAfter(ESCALATED_RUN.slice(0, 4))! },
    }).runs[TEST_DISPUTE_ID];

    const detail = buildCaseDetail({
      ...base,
      record: disputeRecord({ status: "resolved" }),
      recordFetchedAt: NOW + 1,
      run: interrupted,
    });

    expect(detail).toMatchObject({ status: "resolved", run: null, live: false });
  });

  it("keeps a finished run on show while the record agrees with how it ended", () => {
    const afterRefetch = (events: ScriptedEvent[], status: string) =>
      buildCaseDetail({
        ...base,
        record: disputeRecord({ status }),
        recordFetchedAt: NOW + 1,
        run: runAfter(events),
      });

    expect(afterRefetch(FAILED_RUN, "failed")?.run?.error).toBe("Unable to locate credentials");
    expect(afterRefetch(ESCALATED_RUN, "escalated")?.run).not.toBeNull();
    // Approved since: the record has moved on, and the run is history.
    expect(afterRefetch(ESCALATED_RUN, "resolved")).toMatchObject({
      status: "resolved",
      run: null,
    });
  });

  it("tells the whole history, filling in what the trail leaves out", () => {
    const escalated = auditEntry({ decision: { ...ESCALATED_REFUND } });
    const approved = auditEntry({
      engine: "approved",
      gate: "execute",
      executed: true,
      action_taken: "Refunded 59.99 USD",
      created_at: "2026-11-06T09:00:00",
    });

    const history = (status: string, trail = [escalated]) =>
      buildCaseDetail({
        ...base,
        record: disputeRecord({ status, resolved_at: "2026-11-06T10:00:00" }),
        trail,
      })?.history.map((event) => event.kind);

    expect(history("resolved", [approved, escalated])).toEqual(["approved", "escalated"]);
    expect(history("resolved")).toEqual(["acknowledged", "escalated"]);
    expect(history("rejected")).toEqual(["rejected", "escalated"]);
  });

  it("is nothing at all for a dispute no source knows", () => {
    expect(buildCaseDetail({ ...base, record: null })).toBeNull();
  });
});
