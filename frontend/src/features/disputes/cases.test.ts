import { describe, expect, it } from "vitest";

import type { ServerEvent } from "@/features/mediation/events";
import {
  applyServerEvent,
  failRun,
  initialMediationState,
  type MediationState,
  requestRun,
} from "@/features/mediation/store";
import { parseServerTime } from "@/lib/format";
import {
  disputeRecord,
  ESCALATED_RUN,
  openDispute,
  RESOLVED_RUN,
  type ScriptedEvent,
  TEST_DISPUTE_ID,
} from "@/test/fixtures";

import {
  buildCases,
  type Case,
  countByFilter,
  matchesFilter,
  matchesQuery,
  UNFINISHED_AFTER_MS,
} from "./cases";

const NOW = Date.UTC(2026, 10, 7, 12, 0, 0);

/** The runs a tab would hold after these events, all arriving at `at`. */
function runsAfter(events: ScriptedEvent[], at: number, state = initialMediationState) {
  return events.reduce<MediationState>(
    (current, [event, data]) =>
      applyServerEvent(current, { event, data, messageId: "m", timestamp: "t" } as ServerEvent, at),
    state,
  ).runs;
}

const summarize = (cases: Case[]) => cases.map(({ id, status }) => [id, status]);

const DEMO_OPEN = [
  openDispute("FIXTURE-NR-001"),
  openDispute("FIXTURE-NAD-001", { reason: "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED" }),
  openDispute("FIXTURE-UNAUTH-001", { reason: "UNAUTHORISED" }),
];

describe("building the cases list", () => {
  it("trusts Settle's record over the open list, which calls every demo dispute open", () => {
    const cases = buildCases({
      open: DEMO_OPEN,
      records: [
        disputeRecord({
          paypal_dispute_id: "FIXTURE-NAD-001",
          status: "resolved",
          dispute_type: "not_as_described",
          outcome: "refund",
          refund_amount: 20,
          disputed_amount: 32,
        }),
        disputeRecord(),
      ],
      runs: {},
      now: NOW,
    });

    expect(summarize(cases)).toEqual([
      ["FIXTURE-NR-001", "needs_you"],
      ["FIXTURE-UNAUTH-001", "open"],
      ["FIXTURE-NAD-001", "resolved"],
    ]);
    expect(cases[2]).toMatchObject({
      demo: true,
      type: "not_as_described",
      amount: { value: 32, currency: "USD" },
      outcome: "refund",
      refundAmount: 20,
    });
  });

  it("works out the type of a case Settle hasn't seen from PayPal's reason", () => {
    const [item] = buildCases({ open: [DEMO_OPEN[2]!], runs: {}, now: NOW });

    expect(item).toMatchObject({
      status: "open",
      type: "unauthorized_or_other",
      reason: "UNAUTHORISED",
      amount: null,
      updatedAt: null,
    });
  });

  it("tells a rejected case and a failed one apart from those waiting on the seller", () => {
    const cases = buildCases({
      records: [
        disputeRecord({ paypal_dispute_id: "WAITING", status: "escalated" }),
        disputeRecord({ paypal_dispute_id: "DECLINED", status: "rejected" }),
        disputeRecord({ paypal_dispute_id: "BROKE", status: "failed" }),
      ],
      runs: {},
      now: NOW,
    });

    expect(Object.fromEntries(summarize(cases))).toEqual({
      WAITING: "needs_you",
      DECLINED: "rejected",
      BROKE: "unfinished",
    });
  });

  it("reads the open list's own details, and Settle's status where it gives one", () => {
    const cases = buildCases({
      open: [
        openDispute("PP-CLOSED", { status: "resolved", source: "paypal" }),
        openDispute("PP-WAITING", {
          status: "escalated",
          source: "paypal",
          updated_at: "2026-11-07T11:00:00",
        }),
        openDispute("PP-NEW", {
          status: "waiting_for_seller_response",
          source: "paypal",
          amount: 120,
          currency: "EUR",
          item: "Desk lamp",
          dispute_type: "not_as_described",
        }),
      ],
      runs: {},
      now: NOW,
    });

    expect(Object.fromEntries(summarize(cases))).toEqual({
      "PP-WAITING": "needs_you",
      "PP-NEW": "open",
      "PP-CLOSED": "closed",
    });
    expect(cases.find((item) => item.id === "PP-NEW")).toMatchObject({
      demo: false,
      type: "not_as_described",
      item: "Desk lamp",
      amount: { value: 120, currency: "EUR" },
    });
  });

  it("shows a mediation under way from its first event, over an older result", () => {
    const runs = runsAfter(
      RESOLVED_RUN.slice(0, 3),
      NOW,
      requestRun(initialMediationState, TEST_DISPUTE_ID, NOW),
    );
    const [item] = buildCases({
      records: [disputeRecord({ status: "resolved" })],
      recordsFetchedAt: NOW + 1,
      runs,
      now: NOW,
    });

    expect(item).toMatchObject({ status: "mediating", live: true, updatedAt: NOW });
  });

  it("follows a finished run until the lists refetch, then goes by the record", () => {
    const runs = runsAfter(ESCALATED_RUN, NOW);
    const stale = disputeRecord({ status: "mediating", updated_at: "2026-11-07T12:00:00" });

    const before = buildCases({ records: [stale], recordsFetchedAt: NOW - 1, runs, now: NOW });
    expect(before[0]).toMatchObject({ status: "needs_you", live: false });

    const approved = disputeRecord({ status: "resolved", updated_at: "2026-11-07T12:01:00" });
    const after = buildCases({ records: [approved], recordsFetchedAt: NOW + 1, runs, now: NOW });
    expect(after[0]?.status).toBe("resolved");
  });

  it("calls a mediation unfinished once the backend has said it is under way for too long", () => {
    const record = disputeRecord({ status: "mediating", updated_at: "2026-11-07T11:00:00" });
    const updatedAt = parseServerTime(record.updated_at)!;
    const at = (now: number) => buildCases({ records: [record], runs: {}, now })[0]?.status;

    expect(at(updatedAt + 60_000)).toBe("mediating");
    expect(at(updatedAt + UNFINISHED_AFTER_MS + 1)).toBe("unfinished");
  });

  it("shows a run that failed here as unfinished, and leaves out one for an unknown dispute", () => {
    const started = requestRun(initialMediationState, "NOT-A-DISPUTE", NOW);
    const runs = failRun(started, "NOT-A-DISPUTE", "Could not gather the dispute", NOW).runs;
    expect(buildCases({ runs, now: NOW })).toEqual([]);

    const known = buildCases({ open: [openDispute("NOT-A-DISPUTE")], runs, now: NOW });
    expect(known[0]?.status).toBe("unfinished");
  });

  it("puts the most recently updated first within a status", () => {
    const cases = buildCases({
      records: [
        disputeRecord({
          paypal_dispute_id: "OLD",
          status: "resolved",
          updated_at: "2026-11-01T09:00:00",
        }),
        disputeRecord({
          paypal_dispute_id: "NEW",
          status: "resolved",
          updated_at: "2026-11-06T09:00:00",
        }),
      ],
      runs: {},
      now: NOW,
    });

    expect(cases.map((item) => item.id)).toEqual(["NEW", "OLD"]);
  });
});

describe("filtering cases", () => {
  const cases = buildCases({
    open: [
      ...DEMO_OPEN,
      openDispute("PP-1", { status: "resolved", reason: "CREDIT_NOT_PROCESSED", source: "paypal" }),
    ],
    records: [
      disputeRecord(),
      disputeRecord({
        paypal_dispute_id: "FIXTURE-NAD-001",
        status: "mediating",
        dispute_type: "not_as_described",
        reason_code: "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
        updated_at: "2026-11-07T11:59:00",
        buyer_complaint: "The shirt arrived in the wrong size.",
      }),
    ],
    runs: {},
    now: NOW,
  });

  it("counts each filter, with work in progress under open and PayPal's closures under closed", () => {
    expect(countByFilter(cases)).toEqual({ all: 4, needs_you: 1, open: 2, closed: 1 });
    expect(cases.filter((item) => matchesFilter(item, "open")).map((item) => item.id)).toEqual([
      "FIXTURE-NAD-001",
      "FIXTURE-UNAUTH-001",
    ]);
  });

  it("searches ids, types and complaints, every word anywhere", () => {
    const search = (query: string) =>
      cases.filter((item) => matchesQuery(item, query)).map((item) => item.id);

    expect(search("wrong size")).toEqual(["FIXTURE-NAD-001"]);
    expect(search("unauth-001")).toEqual(["FIXTURE-UNAUTH-001"]);
    expect(search("credit")).toEqual(["PP-1"]);
    expect(search("not received")).toEqual(["FIXTURE-NR-001"]);
    expect(search("  ")).toHaveLength(4);
    expect(search("nothing like this")).toEqual([]);
  });
});
