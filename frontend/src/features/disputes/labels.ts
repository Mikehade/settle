import type {
  DisputeType,
  Outcome,
  ReasoningStage,
  TrackingStatus,
} from "@/features/mediation/events";

export const DISPUTE_TYPE_LABELS: Record<DisputeType, string> = {
  not_received: "Not received",
  not_as_described: "Not as described",
  unauthorized_or_other: "Unauthorized or other",
};

export const OUTCOME_LABELS: Record<Outcome, string> = {
  refund: "Refund",
  reship: "Reship",
  accept: "Accept claim",
};

export function asDisputeType(value: string | null | undefined): DisputeType | null {
  return value && value in DISPUTE_TYPE_LABELS ? (value as DisputeType) : null;
}

export function asOutcome(value: string | null | undefined): Outcome | null {
  return value && value in OUTCOME_LABELS ? (value as Outcome) : null;
}

/**
 * The type Settle will give a dispute it hasn't mediated yet, from PayPal's reason code. Mirrors
 * `classify_reason` in `backend/src/domain/core/constants/dispute_types.py`: two reasons have a
 * type of their own and everything else, including no reason, is "unauthorized or other".
 */
export function disputeTypeFromReason(reason: string | null | undefined): DisputeType {
  switch (reason?.trim().toUpperCase()) {
    case "MERCHANDISE_OR_SERVICE_NOT_RECEIVED":
      return "not_received";
    case "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED":
      return "not_as_described";
    default:
      return "unauthorized_or_other";
  }
}

export const STAGE_LABELS: Record<ReasoningStage, string> = {
  classify: "Classify the dispute",
  weigh: "Weigh the evidence",
  policy: "Apply your policy",
  choose: "Choose an outcome",
};

export const STAGES = Object.keys(STAGE_LABELS) as ReasoningStage[];

export const TRACKING_LABELS: Record<TrackingStatus, string> = {
  delivered: "Delivered",
  in_transit: "In transit",
  not_shipped: "Not shipped",
  none: "No tracking",
  unknown: "Unknown",
};

/** "lookup_tracking" to "Lookup tracking". */
export function toolLabel(name: string) {
  const words = name.replaceAll(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The backend's account of an action, without the note it adds to a dry run ("(dry run, no live
 * capture)"), which the interface shows as a badge instead. `null` when there is nothing to say.
 */
export function actionText(text: string | null | undefined) {
  const cleaned = text?.replace(/\s*\(dry run\b[^)]*\)\s*$/i, "").trim();
  return cleaned || null;
}

/** "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" to "Merchandise or service not received". */
export function reasonLabel(code: string) {
  const words = code
    .trim()
    .toLowerCase()
    .replaceAll(/[_\s]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
