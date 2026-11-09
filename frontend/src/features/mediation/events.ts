/**
 * The mediation WebSocket contract: backend `src/api/ws/events.py`, `src/core/mediation.py` and
 * section 3 of `UI_INTEGRATION.md`. It is not part of OpenAPI, so it is typed by hand here. Keep
 * this file in step with those when the backend changes.
 */

/** Close codes the server uses when it refuses the socket's token. */
export const CLOSE_NOT_AUTHENTICATED = 4401;
export const CLOSE_INVALID_TOKEN = 4402;

export type ReasoningStage = "classify" | "weigh" | "policy" | "choose";
export type Outcome = "refund" | "reship" | "accept";
export type DisputeType = "not_received" | "not_as_described" | "unauthorized_or_other";
export type Gate = "execute" | "escalate";
export type TrackingStatus = "delivered" | "in_transit" | "not_shipped" | "none" | "unknown";

/** The facts the mediator reasons over, assembled by the backend before it starts. */
export interface CaseFile {
  dispute_id: string;
  dispute_type?: DisputeType;
  reason_code?: string | null;
  buyer_complaint?: string;
  seller_response?: string;
  item_name?: string | null;
  item_value?: number | null;
  disputed_amount?: number;
  currency?: string;
  transaction_id?: string | null;
  capture_id?: string | null;
  tracking_status?: TrackingStatus;
  tracking_carrier?: string | null;
  tracking_number?: string | null;
  prior_refunds?: number;
  buyer_message_count?: number;
  seller_message_count?: number;
  raw?: Record<string, unknown>;
}

/** The mediator's decision after the guardrails have gated it. Every field may be missing. */
export interface Decision {
  dispute_id?: string;
  dispute_type?: DisputeType;
  /** `null` when the mediator escalates without a clear outcome. */
  outcome?: Outcome | null;
  refund_amount?: number | null;
  /** 0 to 1. */
  confidence?: number;
  rationale?: string;
  classification?: string;
  evidence_summary?: string;
  policy_application?: string;
  gate?: Gate;
  escalation_recommendation?: string | null;
  gate_reason?: string | null;
}

/** What the executor did with an executed decision. Fixture disputes are always dry runs. */
export interface ExecutionResult {
  executed?: boolean;
  dry_run?: boolean;
  gate?: Gate;
  gate_reason?: string | null;
  action_taken?: string;
  paypal_result?: Record<string, unknown>;
}

/** Every event about a run names its dispute, so several runs can stream at once without mixing. */
type ForDispute<T = unknown> = { dispute_id: string } & T;

/** Every event the server sends, with its `data`. */
export interface ServerEvents {
  "connection.ready": { channel: string };
  "connection.error": { message: string };
  "case.detected": ForDispute;
  /** Sent twice: once when gathering starts, again with the assembled case file. */
  "case.gathering": ForDispute<{ case_file?: CaseFile }>;
  /** A stage of the reasoning chain, complete. */
  "case.reasoning_step": ForDispute<{ stage: ReasoningStage; text: string }>;
  /** The mediator's narration as it streams, tagged with its stage when the model marks one. */
  "case.token": ForDispute<{ text: string; stage?: ReasoningStage | null }>;
  "case.tool_call": ForDispute<{ name: string | null; input: Record<string, unknown> }>;
  "case.tool_result": ForDispute<{ name: string | null; ok: boolean }>;
  "case.decision": ForDispute<{ decision: Decision }>;
  "case.escalated": ForDispute<{
    recommendation: string | null;
    gate_reason: string | null;
    decision: Decision;
  }>;
  /** A run carried out its decision, or another client approved one over the socket. */
  "case.executed": ForDispute<{ result: ExecutionResult; decision?: Decision }>;
  /** A run's closing explanation, or another client's rejection over the socket. */
  "case.explained": ForDispute<{ rationale: string; action_taken: string; decision?: Decision }>;
  /**
   * The end of whatever it names, with nothing to follow: a run that failed, or one the server
   * refused to start (`code` says why). With no dispute id, it refuses a malformed request.
   */
  "case.error": { dispute_id?: string; error: string; code?: string };
  "agent.message": { message: string } & Record<string, unknown>;
  "agent.typing": { typing: boolean };
}

export type ServerEventName = keyof ServerEvents;

export type ServerEvent = {
  [Name in ServerEventName]: {
    event: Name;
    data: ServerEvents[Name];
    messageId: string;
    timestamp: string;
  };
}[ServerEventName];

/**
 * Every event the client sends. Some of the socket's actions go over REST instead:
 * - approve and reject, because REST answers each request with its result or an error. Over the
 *   socket, a lost reply would leave the seller not knowing whether money moved.
 * - `seller.set_policy`, because the REST endpoint validates the change and returns the result.
 */
export interface ClientEvents {
  "seller.mediate": { dispute_id: string };
  "seller.message": { text: string };
  ping: Record<string, never>;
}

export type ClientEvent = {
  [Name in keyof ClientEvents]: { event: Name; data: ClientEvents[Name] };
}[keyof ClientEvents];

const SERVER_EVENT_NAMES = {
  "connection.ready": true,
  "connection.error": true,
  "case.detected": true,
  "case.gathering": true,
  "case.reasoning_step": true,
  "case.token": true,
  "case.tool_call": true,
  "case.tool_result": true,
  "case.decision": true,
  "case.escalated": true,
  "case.executed": true,
  "case.explained": true,
  "case.error": true,
  "agent.message": true,
  "agent.typing": true,
} satisfies Record<ServerEventName, true>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isServerEventName(name: unknown): name is ServerEventName {
  return typeof name === "string" && Object.hasOwn(SERVER_EVENT_NAMES, name);
}

/**
 * Reads one frame from the server. Returns `null` for anything that is not a known event in the
 * envelope `{ event, message_id, data, timestamp }`, or a run's event without its dispute id.
 * The rest of the payload is trusted as typed.
 */
export function parseServerEvent(raw: unknown): ServerEvent | null {
  if (typeof raw !== "string") return null;
  let frame: unknown;
  try {
    frame = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(frame) || !isServerEventName(frame.event) || !isRecord(frame.data)) return null;
  // A run's events are routed by their dispute id; one without it can't go anywhere.
  const needsDispute = frame.event.startsWith("case.") && frame.event !== "case.error";
  if (needsDispute && typeof frame.data.dispute_id !== "string") return null;

  return {
    event: frame.event,
    data: frame.data,
    messageId: typeof frame.message_id === "string" ? frame.message_id : "",
    timestamp: typeof frame.timestamp === "string" ? frame.timestamp : "",
  } as ServerEvent;
}
