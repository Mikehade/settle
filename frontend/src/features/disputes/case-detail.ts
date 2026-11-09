import type { CaseFile, Decision, DisputeType } from "@/features/mediation/events";
import { isActive, isFinished, type Run } from "@/features/mediation/store";
import type { AuditEntry, DisputePreview, DisputeRecord } from "@/lib/api/types";
import { parseServerTime } from "@/lib/format";

import { type CaseStatus, caseStatusOf } from "./cases";
import { actionText, asDisputeType, disputeTypeFromReason } from "./labels";

/** What the mediator decided, and what came of it, from a live run or the audit trail. */
export interface CaseDecision {
  decision: Decision;
  recommendation: string | null;
  gateReason: string | null;
  /** The closing explanation, for both the buyer and the seller. */
  rationale: string | null;
  actionTaken: string | null;
  /** Money moved, or a reply went to PayPal. False for a dry run or an escalation. */
  executed: boolean | null;
  /** A demo dispute's action, simulated rather than sent to PayPal. */
  dryRun: boolean;
  decidedAt: number | null;
}

/** One line of a case's history. */
export interface CaseEvent {
  kind: "escalated" | "executed" | "approved" | "acknowledged" | "rejected";
  at: number | null;
  actionTaken: string | null;
}

export interface CaseDetail {
  id: string;
  status: CaseStatus;
  /** A seeded demo dispute rather than a real one from PayPal. */
  demo: boolean;
  type: DisputeType;
  caseFile: CaseFile | null;
  /** The run to show as it happens, while it is fresher than what the backend last said. */
  run: Run | null;
  live: boolean;
  /** The latest decision, from the run when it is the one shown, otherwise from the trail. */
  latest: CaseDecision | null;
  /** The seller can approve or reject now. */
  awaitingReview: boolean;
  /** Can be mediated: never mediated, or the last run ended without a decision. */
  canMediate: boolean;
  history: CaseEvent[];
  updatedAt: number | null;
}

interface CaseDetailSources {
  id: string;
  record: DisputeRecord | null | undefined;
  /** When `record` was fetched, by this browser's clock. */
  recordFetchedAt: number;
  preview: DisputePreview | undefined;
  trail: AuditEntry[] | undefined;
  run: Run | undefined;
  now: number;
}

function fromRun(run: Run): CaseDecision | null {
  if (!run.decision) return null;
  return {
    decision: run.decision,
    recommendation:
      run.escalation?.recommendation ?? run.decision.escalation_recommendation ?? null,
    gateReason: run.escalation?.gateReason ?? run.decision.gate_reason ?? null,
    rationale: run.explanation?.rationale ?? run.decision.rationale ?? null,
    actionTaken: actionText(run.explanation?.actionTaken ?? run.execution?.action_taken),
    executed: run.execution?.executed ?? (run.escalation ? false : null),
    dryRun: run.execution?.dry_run ?? false,
    decidedAt: run.updatedAt,
  };
}

/** A decision as the audit trail recorded it. */
export function fromEntry(entry: AuditEntry): CaseDecision {
  const decision = entry.decision as Decision;
  return {
    decision,
    recommendation: decision.escalation_recommendation ?? null,
    gateReason: decision.gate_reason ?? null,
    rationale: decision.rationale ?? null,
    actionTaken: actionText(entry.action_taken),
    executed: entry.executed,
    dryRun: entry.paypal_result.dry_run === true,
    decidedAt: parseServerTime(entry.created_at),
  };
}

/**
 * The history the trail and the record tell together. The trail has an entry for each decision
 * the mediator made and each approval that moved money; the record's terminal status and date
 * fill in what the trail leaves out (a rejection, or approving an escalation with no action).
 */
function historyOf(record: DisputeRecord | null | undefined, trail: AuditEntry[]): CaseEvent[] {
  const events: CaseEvent[] = trail.map((entry) => ({
    kind:
      entry.engine === "approved"
        ? "approved"
        : entry.gate === "escalate"
          ? "escalated"
          : "executed",
    at: parseServerTime(entry.created_at),
    actionTaken: actionText(entry.action_taken),
  }));
  const latest = trail[0];
  const closedAt = parseServerTime(record?.resolved_at);
  if (record?.status === "rejected") {
    events.unshift({ kind: "rejected", at: closedAt, actionTaken: null });
  } else if (record?.status === "resolved" && latest?.gate === "escalate") {
    events.unshift({ kind: "acknowledged", at: closedAt, actionTaken: null });
  }
  return events;
}

/** Whether the backend's status for a dispute is where this finished run left it. */
function agrees(run: Run, status: string | undefined) {
  switch (run.status) {
    // A run can fail before the backend records the dispute, which then still reads as open.
    case "failed":
      return status === undefined || status === "failed" || status === "open";
    case "escalated":
      return status === "escalated";
    case "resolved":
      return status === "resolved";
    default:
      return false;
  }
}

/** Everything the case page shows about one dispute, or `null` when there is no such case. */
export function buildCaseDetail({
  id,
  record,
  recordFetchedAt,
  preview,
  trail = [],
  run,
  now,
}: CaseDetailSources): CaseDetail | null {
  const live = run !== undefined && isActive(run) && !run.interrupted;
  // As on the cases list, a run that changed since the record was fetched is the freshest word.
  // A finished run stays on show while the record agrees with how it ended: its trace (and the
  // reason it failed) says more than the record does.
  const shownRun =
    run &&
    (live ||
      run.updatedAt > recordFetchedAt ||
      (isFinished(run) && agrees(run, record?.status ?? preview?.status)))
      ? run
      : null;
  const recordUpdatedAt = parseServerTime(record?.updated_at);

  let status: CaseStatus | null = null;
  if (shownRun) {
    status = isActive(shownRun)
      ? "mediating"
      : shownRun.status === "escalated"
        ? "needs_you"
        : shownRun.status === "resolved"
          ? "resolved"
          : "unfinished";
  } else if (record) {
    status = caseStatusOf(record.status, recordUpdatedAt, now);
  } else if (preview) {
    status = caseStatusOf(preview.status, null, now);
  }
  if (!status) return null;

  const caseFile =
    shownRun?.caseFile ??
    (record?.case_file as CaseFile | undefined) ??
    (preview?.case_file as CaseFile | undefined) ??
    run?.caseFile ??
    null;
  const latestEntry = trail[0];
  const latest = shownRun ? fromRun(shownRun) : latestEntry ? fromEntry(latestEntry) : null;
  const reason = record?.reason_code ?? caseFile?.reason_code ?? null;

  return {
    id,
    status,
    demo: (record?.source ?? "") === "fixture" || id.startsWith("FIXTURE-"),
    type:
      asDisputeType(record?.dispute_type) ??
      caseFile?.dispute_type ??
      disputeTypeFromReason(reason),
    caseFile,
    run: shownRun,
    live,
    latest,
    // Only once the run is over: until then the backend is still recording the escalation.
    awaitingReview: status === "needs_you" && (!shownRun || isFinished(shownRun)),
    canMediate: (status === "open" || status === "unfinished") && !live,
    history: historyOf(record, trail),
    updatedAt: shownRun?.updatedAt ?? recordUpdatedAt,
  };
}
