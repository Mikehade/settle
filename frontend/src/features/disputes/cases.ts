import type { CaseFile, DisputeType, Outcome } from "@/features/mediation/events";
import { isActive, type Run } from "@/features/mediation/store";
import type { DisputeRecord, OpenDispute } from "@/lib/api/types";
import { parseServerTime } from "@/lib/format";

import {
  asDisputeType,
  asOutcome,
  DISPUTE_TYPE_LABELS,
  disputeTypeFromReason,
  OUTCOME_LABELS,
} from "./labels";

/**
 * Where a case stands, from the seller's side.
 * - `needs_you`: the guardrails escalated it, and the seller must approve or reject.
 * - `mediating`: a mediation is under way.
 * - `unfinished`: a mediation ended without a decision, and can be run again.
 * - `open`: Settle hasn't mediated it.
 * - `resolved`: Settle carried out a decision, or the seller approved one.
 * - `rejected`: the seller declined the recommendation and is handling it in PayPal.
 * - `closed`: PayPal closed it without Settle.
 */
export type CaseStatus =
  "needs_you" | "mediating" | "unfinished" | "open" | "resolved" | "rejected" | "closed";

export interface Case {
  /** PayPal's dispute id, which is also how the mediator and the case page refer to it. */
  id: string;
  status: CaseStatus;
  /** Its mediation is streaming to this tab right now. */
  live: boolean;
  /** A seeded demo dispute rather than a real one from PayPal. */
  demo: boolean;
  type: DisputeType;
  /** PayPal's reason code, when known. */
  reason: string | null;
  item: string | null;
  amount: { value: number; currency: string } | null;
  /** What Settle did. Only resolved cases have one. */
  outcome: Outcome | null;
  refundAmount: number | null;
  /** The buyer's complaint, once Settle has gathered the case. */
  complaint: string | null;
  /** When anything last changed, as epoch milliseconds. */
  updatedAt: number | null;
}

/**
 * How long the backend may report a mediation as under way before it counts as unfinished. The
 * backend marks a run that fails as `failed`, but one cut off by a server restart stays
 * "mediating"; a real run takes seconds to a few minutes.
 */
export const UNFINISHED_AFTER_MS = 10 * 60_000;

/** Needs attention first, then work in progress, then the rest, newest first. */
const STATUS_ORDER: Record<CaseStatus, number> = {
  needs_you: 0,
  mediating: 1,
  unfinished: 2,
  open: 3,
  resolved: 4,
  rejected: 4,
  closed: 4,
};

/** The case status for a status Settle's backend gave a dispute. */
export function caseStatusOf(status: string, updatedAt: number | null, now: number): CaseStatus {
  switch (status) {
    case "escalated":
      return "needs_you";
    case "resolved":
      return "resolved";
    case "rejected":
      return "rejected";
    case "failed":
      return "unfinished";
    case "mediating":
      return updatedAt !== null && now - updatedAt > UNFINISHED_AFTER_MS
        ? "unfinished"
        : "mediating";
    default:
      return "open";
  }
}

/**
 * The open list gives Settle's status for a dispute the seller has had mediated, with its dates,
 * and otherwise the source's own status, where only "resolved" means anything: PayPal closed it.
 */
function statusFromSummary(summary: OpenDispute, now: number): CaseStatus {
  const updatedAt = parseServerTime(summary.updated_at);
  if (updatedAt !== null) return caseStatusOf(summary.status, updatedAt, now);
  return summary.status === "resolved" ? "closed" : "open";
}

/** A run this tab followed, while it is newer than what the backend last said. */
function statusFromRun(run: Run): CaseStatus {
  if (isActive(run)) return "mediating";
  if (run.status === "escalated") return "needs_you";
  if (run.status === "resolved") return "resolved";
  return "unfinished";
}

interface CaseSources {
  open?: OpenDispute[];
  records?: DisputeRecord[];
  /** When `records` was fetched, by this browser's clock (the query's `dataUpdatedAt`). */
  recordsFetchedAt?: number;
  runs: Record<string, Run>;
  now: number;
}

/**
 * One row per dispute, merged from three places: the open disputes, the disputes Settle has
 * recorded, and the mediations this tab is following live. Sorted with what needs the seller first.
 */
export function buildCases({
  open = [],
  records = [],
  recordsFetchedAt = 0,
  runs,
  now,
}: CaseSources): Case[] {
  const openById = new Map(open.map((summary) => [summary.dispute_id, summary]));
  const recordById = new Map<string, DisputeRecord>();
  // Newest first, so a duplicate from a page boundary moving under us keeps the newer copy.
  for (const record of records) {
    if (!recordById.has(record.paypal_dispute_id)) {
      recordById.set(record.paypal_dispute_id, record);
    }
  }

  const ids = new Set([...openById.keys(), ...recordById.keys(), ...Object.keys(runs)]);
  const cases: Case[] = [];

  for (const id of ids) {
    const summary = openById.get(id);
    const record = recordById.get(id);
    const run = runs[id];
    const live = run !== undefined && isActive(run) && !run.interrupted;
    const recordUpdatedAt = parseServerTime(record?.updated_at);

    let status: CaseStatus | null = null;
    let updatedAt = recordUpdatedAt ?? parseServerTime(summary?.updated_at);
    // The backend records how a run ended before it says so, and the lists refetch once a run
    // ends. So a run that changed after the last fetch is the freshest word on the case. Both
    // times are this browser's, so a clock that disagrees with the server's can't mislead it.
    if (run && (live || run.updatedAt > recordsFetchedAt)) {
      const fromRun = statusFromRun(run);
      // A run that failed for a dispute neither list knows (a mistyped id, say) is no case at all.
      if (fromRun !== "unfinished" || record || summary) {
        status = fromRun;
        updatedAt = run.updatedAt;
      }
    }
    if (!status && record) status = caseStatusOf(record.status, recordUpdatedAt, now);
    if (!status && summary) status = statusFromSummary(summary, now);
    if (!status) continue;

    const caseFile = run?.caseFile ?? (record?.case_file as CaseFile | undefined);
    const reason = record?.reason_code ?? caseFile?.reason_code ?? summary?.reason ?? null;
    const amountValue = record?.disputed_amount ?? caseFile?.disputed_amount ?? summary?.amount;
    const currency = record?.currency ?? caseFile?.currency ?? summary?.currency;
    const decision = run?.decision;

    cases.push({
      id,
      status,
      live,
      demo: (record?.source ?? summary?.source) === "fixture" || id.startsWith("FIXTURE-"),
      type:
        asDisputeType(record?.dispute_type) ??
        caseFile?.dispute_type ??
        asDisputeType(summary?.dispute_type) ??
        disputeTypeFromReason(reason),
      reason,
      item: caseFile?.item_name ?? summary?.item ?? null,
      amount: amountValue != null && currency ? { value: amountValue, currency } : null,
      outcome:
        status === "resolved" ? (asOutcome(record?.outcome) ?? decision?.outcome ?? null) : null,
      refundAmount:
        status === "resolved" ? (record?.refund_amount ?? decision?.refund_amount ?? null) : null,
      complaint: record?.buyer_complaint || caseFile?.buyer_complaint || null,
      updatedAt,
    });
  }

  return cases.sort(
    (a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      (b.updatedAt ?? -Infinity) - (a.updatedAt ?? -Infinity) ||
      a.id.localeCompare(b.id),
  );
}

export const CASE_FILTERS = ["all", "needs_you", "open", "closed"] as const;
export type CaseFilter = (typeof CASE_FILTERS)[number];

const FILTER_OF: Record<CaseStatus, Exclude<CaseFilter, "all">> = {
  needs_you: "needs_you",
  mediating: "open",
  unfinished: "open",
  open: "open",
  resolved: "closed",
  rejected: "closed",
  closed: "closed",
};

export function matchesFilter(item: Case, filter: CaseFilter) {
  return filter === "all" || FILTER_OF[item.status] === filter;
}

export function countByFilter(cases: Case[]): Record<CaseFilter, number> {
  const counts = { all: cases.length, needs_you: 0, open: 0, closed: 0 };
  for (const item of cases) counts[FILTER_OF[item.status]] += 1;
  return counts;
}

/** Whether every word of `query` appears in the case's id, type, reason, item, outcome or complaint. */
export function matchesQuery(item: Case, query: string) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = [
    item.id,
    DISPUTE_TYPE_LABELS[item.type],
    item.reason?.replaceAll("_", " "),
    item.item,
    item.outcome && OUTCOME_LABELS[item.outcome],
    item.complaint,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words.every((word) => haystack.includes(word));
}
