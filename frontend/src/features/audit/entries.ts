import { actionText } from "@/features/disputes/labels";
import type { AuditListItem } from "@/lib/api/types";

type EntryFacts = Pick<AuditListItem, "gate" | "executed" | "action_taken" | "engine">;

/**
 * What came of a decision:
 * - `carried_out`: it passed the guardrails and went to PayPal.
 * - `dry_run`: it passed the guardrails but was simulated, as it always is for a demo dispute.
 * - `sent_to_you`: the guardrails escalated it.
 * - `failed`: it passed the guardrails but PayPal turned it down, so it was escalated instead.
 */
export type EntryResult = "carried_out" | "dry_run" | "sent_to_you" | "failed";

/**
 * A list row has no `dry_run` flag or failure reason, so this reads them the way the backend
 * writes them (`backend/src/infrastructure/services/executor.py`): a decision that passed the
 * guardrails without being executed was a dry run, and a failed execution is an escalation whose
 * action text starts "Execution failed".
 */
export function resultOf(entry: EntryFacts): EntryResult {
  if (entry.gate === "execute") return entry.executed ? "carried_out" : "dry_run";
  return /^execution failed/i.test(entry.action_taken.trim()) ? "failed" : "sent_to_you";
}

/** Approving an escalation records an entry of its own, carried out on the seller's word. */
export function approvedBySeller(entry: Pick<AuditListItem, "engine">) {
  return entry.engine === "approved";
}

/** One line on what reached PayPal. */
export function whatHappened(entry: EntryFacts) {
  const result = resultOf(entry);
  if (result === "sent_to_you") return "Nothing sent to PayPal";
  if (result === "failed") return "PayPal didn't accept it, so it came to you";
  const action = actionText(entry.action_taken) ?? "Carried out";
  return approvedBySeller(entry) ? `Approved by you · ${action}` : action;
}

const ENGINE_LABELS: Record<string, string> = {
  llm_tools: "Mediator",
  langgraph: "Mediator (LangGraph)",
  approved: "Your approval",
};

export function engineLabel(engine: string) {
  return ENGINE_LABELS[engine] ?? engine;
}
