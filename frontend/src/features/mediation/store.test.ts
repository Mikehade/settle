import { describe, expect, it } from "vitest";

import {
  ESCALATED_RUN,
  FAILED_RUN,
  RESOLVED_RUN,
  type ScriptedEvent,
  TEST_DISPUTE_ID,
} from "@/test/fixtures";

import type { ServerEvent } from "./events";
import {
  applyServerEvent,
  failRun,
  initialMediationState,
  isActive,
  isFinished,
  markDropped,
  type MediationState,
  requestRun,
} from "./store";

function play(state: MediationState, events: ScriptedEvent[]) {
  return events.reduce(
    (current, [event, data]) =>
      applyServerEvent(current, { event, data, messageId: "m", timestamp: "t" } as ServerEvent, 0),
    state,
  );
}

/** The same events, about another dispute. */
const about = (disputeId: string, events: ScriptedEvent[]) =>
  events.map(([event, data]) => [event, { ...data, dispute_id: disputeId }] as ScriptedEvent);

const requested = () => requestRun(initialMediationState, TEST_DISPUTE_ID, 0);

describe("applying server events", () => {
  it("follows an escalated run to the end", () => {
    const run = play(requested(), ESCALATED_RUN).runs[TEST_DISPUTE_ID];

    expect(run).toMatchObject({
      status: "escalated",
      startedHere: true,
      caseFile: { item_name: "Wireless earbuds" },
      error: null,
      escalation: {
        recommendation: "Review this dispute manually and respond in the PayPal Resolution Center.",
        gateReason: "Mediator chose to escalate.",
      },
      explanation: { actionTaken: "Escalated to the seller" },
    });
    expect(run?.steps.map((step) => step.stage)).toEqual(["classify", "weigh", "choose"]);
    expect(isFinished(run)).toBe(true);
  });

  it("collects the narration by stage and pairs each tool call with its result", () => {
    const run = play(requested(), RESOLVED_RUN).runs[TEST_DISPUTE_ID];

    expect(run).toMatchObject({
      status: "resolved",
      execution: { dry_run: true, executed: false },
      decision: { outcome: "refund", refund_amount: 59.99 },
      narration: {
        other: "Let me look at this case. ",
        classify: "The buyer says the parcel never arrived.",
        weigh: "Tracking shows it never shipped.",
      },
    });
    expect(run?.tools).toEqual([
      { name: "lookup_tracking", input: { dispute_id: TEST_DISPUTE_ID }, ok: true },
      { name: "propose_refund", input: { amount: 59.99 }, ok: true },
    ]);
    expect(run?.steps).toHaveLength(4);
  });

  it("follows several runs at once without mixing them up", () => {
    const other = about("FIXTURE-NAD-001", ESCALATED_RUN);
    const interleaved = RESOLVED_RUN.flatMap((event, index) =>
      other[index] ? [event, other[index]] : [event],
    );

    const { runs } = play(requested(), interleaved);

    expect(runs[TEST_DISPUTE_ID]).toMatchObject({ status: "resolved", startedHere: true });
    expect(runs["FIXTURE-NAD-001"]).toMatchObject({ status: "escalated", startedHere: false });
    expect(runs["FIXTURE-NAD-001"]?.tools).toEqual([]);
  });

  it("joins a run started somewhere else, even midway", () => {
    const { runs } = play(initialMediationState, RESOLVED_RUN.slice(5));

    expect(runs[TEST_DISPUTE_ID]).toMatchObject({ status: "resolved", startedHere: false });
  });

  it("ends a run at an error, since nothing follows one", () => {
    const run = play(requested(), FAILED_RUN).runs[TEST_DISPUTE_ID];

    expect(run).toMatchObject({ status: "failed", error: "Unable to locate credentials" });
    expect(isFinished(run)).toBe(true);
  });

  it("fails a run the server refuses to start", () => {
    const refused: ScriptedEvent[] = [
      ...ESCALATED_RUN.slice(0, 2),
      [
        "case.error",
        {
          dispute_id: TEST_DISPUTE_ID,
          error: "This dispute is already being mediated or has been resolved.",
          code: "DISPUTE_ALREADY_RESOLVED",
        },
      ],
    ];

    expect(play(requested(), refused).runs[TEST_DISPUTE_ID]).toMatchObject({
      status: "failed",
      error: "This dispute is already being mediated or has been resolved.",
    });
  });

  it("starts over when a dispute is mediated again", () => {
    let state = play(requested(), FAILED_RUN);
    state = play(state, ESCALATED_RUN);

    expect(state.runs[TEST_DISPUTE_ID]).toMatchObject({ status: "escalated", error: null });
  });

  it("leaves another client's approval or rejection to the lists", () => {
    const finished = play(requested(), ESCALATED_RUN);
    const after = play(finished, [
      [
        "case.executed",
        {
          dispute_id: TEST_DISPUTE_ID,
          result: { executed: true, action_taken: "Refunded 59.99 USD" },
        },
      ],
      [
        "case.explained",
        { dispute_id: "FIXTURE-NAD-001", rationale: "Declined.", action_taken: "Rejected" },
      ],
      ["case.error", { error: "dispute_id is required" }],
    ]);

    expect(after).toBe(finished);
  });
});

describe("local changes", () => {
  it("is active from the request until a decision, and finished once explained", () => {
    let state = requested();
    expect(isActive(state.runs[TEST_DISPUTE_ID])).toBe(true);

    state = play(state, ESCALATED_RUN.slice(0, -1));
    expect(isActive(state.runs[TEST_DISPUTE_ID])).toBe(false);
    expect(isFinished(state.runs[TEST_DISPUTE_ID])).toBe(false);

    state = play(state, ESCALATED_RUN.slice(-1));
    expect(isFinished(state.runs[TEST_DISPUTE_ID])).toBe(true);
  });

  it("fails only unfinished runs", () => {
    const failed = failRun(play(requested(), RESOLVED_RUN.slice(0, 5)), TEST_DISPUTE_ID, "Stopped");
    expect(failed.runs[TEST_DISPUTE_ID]).toMatchObject({ status: "failed", error: "Stopped" });

    const finished = play(requested(), RESOLVED_RUN);
    expect(failRun(finished, TEST_DISPUTE_ID, "Stopped")).toBe(finished);
  });

  it("flags the runs under way when the connection drops, and only those", () => {
    let state = play(requested(), RESOLVED_RUN.slice(0, 5));
    state = play(state, about("FIXTURE-NAD-001", ESCALATED_RUN));
    state = markDropped(state);

    expect(state.runs[TEST_DISPUTE_ID]?.interrupted).toBe(true);
    expect(state.runs["FIXTURE-NAD-001"]?.interrupted).toBe(false);
  });
});
