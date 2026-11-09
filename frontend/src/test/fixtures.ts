import type {
  CaseFile,
  Decision,
  ServerEventName,
  ServerEvents,
} from "@/features/mediation/events";
import type { AuditEntry, DisputeRecord, OpenDispute, User } from "@/lib/api/types";

export const TEST_PASSWORD = "correct-horse-battery";
export const TEST_TOKEN = "test-access-token";

export const TEST_USER: User = {
  id: "8b0f6a52-2f43-4f7e-9d1a-6c5b2f0e9a11",
  email: "ada@seller.test",
  full_name: "Ada Lovelace",
  is_active: true,
  is_superuser: false,
  created_at: "2026-11-01T09:00:00Z",
};

/** A success body in the backend's envelope. */
export function envelope<T>(data: T, meta: Record<string, unknown> | null = null) {
  return { status: "success", code: "OK", message: "OK", data, errors: null, meta };
}

/** An error body in the backend's envelope. */
export function errorEnvelope(
  code: string,
  message: string,
  errors: { field: string; message: string; code?: string }[] | null = null,
) {
  return { status: "error", code, message, data: null, errors, meta: { request_id: "req-test" } };
}

/** One server frame on the mediation socket, as the backend sends it. */
export function frame<Name extends ServerEventName>(event: Name, data: ServerEvents[Name]) {
  return JSON.stringify({
    event,
    message_id: crypto.randomUUID(),
    data,
    timestamp: "2026-11-05T12:00:00Z",
  });
}

export type ScriptedEvent = {
  [Name in ServerEventName]: [Name, ServerEvents[Name]];
}[ServerEventName];

export const TEST_DISPUTE_ID = "FIXTURE-NR-001";

const CASE_FILE: CaseFile = {
  dispute_id: TEST_DISPUTE_ID,
  dispute_type: "not_received",
  reason_code: "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
  buyer_complaint: "I ordered this three weeks ago and it never arrived.",
  seller_response: "We shipped it; sometimes the carrier is slow.",
  item_name: "Wireless earbuds",
  disputed_amount: 59.99,
  currency: "USD",
  tracking_status: "not_shipped",
};

/** Every event of a run names its dispute. */
const forTest = <T extends object>(data: T) => ({ dispute_id: TEST_DISPUTE_ID, ...data });

const NO_PROPOSAL: Decision = {
  dispute_id: TEST_DISPUTE_ID,
  dispute_type: "not_received",
  outcome: null,
  confidence: 0,
  rationale: "The mediator could not reach a confident decision.",
  classification: "not_received",
  evidence_summary: "No proposal tool was called.",
  policy_application: "",
  gate: "escalate",
  escalation_recommendation:
    "Review this dispute manually and respond in the PayPal Resolution Center.",
  gate_reason: "Mediator chose to escalate.",
};

/** A run the guardrails escalate, in the order the backend sends it. */
export const ESCALATED_RUN: ScriptedEvent[] = [
  ["case.detected", forTest({})],
  ["case.gathering", forTest({})],
  ["case.gathering", forTest({ case_file: CASE_FILE })],
  ["case.reasoning_step", forTest({ stage: "classify" as const, text: "not_received" })],
  [
    "case.reasoning_step",
    forTest({ stage: "weigh" as const, text: "No proposal tool was called." }),
  ],
  [
    "case.reasoning_step",
    forTest({ stage: "choose" as const, text: "escalate (confidence 0.00)" }),
  ],
  ["case.decision", forTest({ decision: NO_PROPOSAL })],
  [
    "case.escalated",
    forTest({
      recommendation: NO_PROPOSAL.escalation_recommendation ?? null,
      gate_reason: "Mediator chose to escalate.",
      decision: NO_PROPOSAL,
    }),
  ],
  [
    "case.explained",
    forTest({
      rationale: "The mediator could not reach a confident decision.",
      action_taken: "Escalated to the seller",
      decision: NO_PROPOSAL,
    }),
  ],
];

/**
 * A run that fails, as every run does on a backend with no model available: the case is gathered,
 * then the model call fails and nothing follows the error.
 */
export const FAILED_RUN: ScriptedEvent[] = [
  ["case.detected", forTest({})],
  ["case.gathering", forTest({})],
  ["case.gathering", forTest({ case_file: CASE_FILE })],
  ["case.error", forTest({ error: "Unable to locate credentials" })],
];

const REFUND: Decision = {
  dispute_id: TEST_DISPUTE_ID,
  dispute_type: "not_received",
  outcome: "refund",
  refund_amount: 59.99,
  confidence: 0.95,
  rationale: "Tracking shows the label was created but the parcel never shipped.",
  gate: "execute",
  gate_reason: "Within guardrails.",
};

/** A run the mediator carries out itself: a full refund, as a dry run, narrated stage by stage. */
export const RESOLVED_RUN: ScriptedEvent[] = [
  ["case.detected", forTest({})],
  ["case.gathering", forTest({})],
  ["case.gathering", forTest({ case_file: CASE_FILE })],
  ["case.token", forTest({ text: "Let me look at this case. " })],
  ["case.token", forTest({ text: "The buyer says the parcel ", stage: "classify" as const })],
  ["case.token", forTest({ text: "never arrived.", stage: "classify" as const })],
  [
    "case.reasoning_step",
    forTest({ stage: "classify" as const, text: "The buyer says the parcel never arrived." }),
  ],
  ["case.tool_call", forTest({ name: "lookup_tracking", input: { dispute_id: TEST_DISPUTE_ID } })],
  ["case.tool_result", forTest({ name: "lookup_tracking", ok: true })],
  ["case.token", forTest({ text: "Tracking shows it never shipped.", stage: "weigh" as const })],
  [
    "case.reasoning_step",
    forTest({ stage: "weigh" as const, text: "Tracking shows it never shipped." }),
  ],
  [
    "case.token",
    forTest({ text: "Refund in full when nothing shipped.", stage: "policy" as const }),
  ],
  [
    "case.reasoning_step",
    forTest({ stage: "policy" as const, text: "Refund in full when nothing shipped." }),
  ],
  ["case.tool_call", forTest({ name: "propose_refund", input: { amount: 59.99 } })],
  ["case.tool_result", forTest({ name: "propose_refund", ok: true })],
  ["case.token", forTest({ text: "A full refund.", stage: "choose" as const })],
  ["case.reasoning_step", forTest({ stage: "choose" as const, text: "A full refund." })],
  ["case.decision", forTest({ decision: REFUND })],
  [
    "case.executed",
    forTest({
      result: {
        executed: false,
        dry_run: true,
        gate: "execute" as const,
        action_taken: "Refunded 59.99 USD (dry run, no live capture)",
      },
      decision: REFUND,
    }),
  ],
  [
    "case.explained",
    forTest({
      rationale: "Tracking shows the label was created but the parcel never shipped.",
      action_taken: "Refunded 59.99 USD (dry run, no live capture)",
      decision: REFUND,
    }),
  ],
];

/** A dispute as Settle recorded it. Defaults to the escalated demo case; override what a test needs. */
export function disputeRecord(overrides: Partial<DisputeRecord> = {}): DisputeRecord {
  return {
    id: crypto.randomUUID(),
    seller_id: TEST_USER.id,
    paypal_dispute_id: TEST_DISPUTE_ID,
    status: "escalated",
    dispute_type: "not_received",
    reason_code: "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    disputed_amount: 59.99,
    currency: "USD",
    buyer_complaint: CASE_FILE.buyer_complaint ?? "",
    seller_response: CASE_FILE.seller_response ?? "",
    case_file: { ...CASE_FILE },
    outcome: null,
    refund_amount: null,
    confidence: 0,
    source: "fixture",
    // Without an offset, the way the backend sends them.
    created_at: "2026-11-05T14:49:35",
    updated_at: "2026-11-05T14:49:36",
    // Only final statuses get a date; an escalated case is still waiting.
    resolved_at: null,
    ...overrides,
  };
}

/** A dispute in the open list. Demo ones are always "open" there, whatever Settle did with them. */
export function openDispute(id: string, overrides: Partial<OpenDispute> = {}): OpenDispute {
  return {
    dispute_id: id,
    status: "open",
    reason: "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    source: "fixture",
    ...overrides,
  };
}

/** One decision in a dispute's audit trail. Defaults to the escalated demo case's. */
export function auditEntry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: crypto.randomUUID(),
    dispute_id: crypto.randomUUID(),
    seller_id: TEST_USER.id,
    paypal_dispute_id: TEST_DISPUTE_ID,
    case_file: { ...CASE_FILE },
    decision: { ...NO_PROPOSAL },
    outcome: null,
    confidence: 0,
    gate: "escalate",
    action_taken: "Escalated to the seller",
    executed: false,
    paypal_result: { escalated: true },
    engine: "llm_tools",
    served_by: null,
    created_at: "2026-11-05T14:49:36",
    ...overrides,
  };
}

/** The refund the mediator recommends but the guardrails escalate, for approval tests. */
export const ESCALATED_REFUND: Decision = {
  ...REFUND,
  gate: "escalate",
  gate_reason: "Refund is above your auto-approve limit.",
  escalation_recommendation: "Refund the buyer in full.",
};
