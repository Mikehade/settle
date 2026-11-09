import { z } from "zod";

import type { Policy, PolicyUpdate } from "@/lib/api/types";

export type LimitKey = Exclude<keyof PolicyUpdate, "rules_text">;

export const RULES_MAX = 4000;

/**
 * The backend's built-in limits (`backend/src/domain/core/constants/guardrails.py`), which apply
 * wherever a policy leaves one empty. A server can override the first three with its
 * `GUARDRAIL_*` settings; the API doesn't say when it has.
 */
export const DEFAULT_LIMITS = {
  confidence_threshold: 0.8,
  human_in_loop_amount: 200,
  partial_refund_ceiling: 150,
  /** Falls back to the human-review amount. */
  auto_accept_max: null,
  /** Off. */
  always_refund_under: 0,
} satisfies Record<LimitKey, number | null>;

interface LimitDefinition {
  key: LimitKey;
  label: string;
  description: string;
  kind: "percent" | "amount";
}

/** In the order the backend checks them. */
export const LIMITS: LimitDefinition[] = [
  {
    key: "confidence_threshold",
    label: "Confidence needed to act alone",
    description: "Below this, Settle brings the case to you, however clear-cut it looks.",
    kind: "percent",
  },
  {
    key: "human_in_loop_amount",
    label: "Amount that always comes to you",
    description: "Disputes for this much or more are never settled without you.",
    kind: "amount",
  },
  {
    key: "partial_refund_ceiling",
    label: "Largest refund Settle gives alone",
    description: "Refunds above this come to you to approve.",
    kind: "amount",
  },
  {
    key: "auto_accept_max",
    label: "Largest claim Settle accepts alone",
    description: "Accepting a claim above this comes to you. Empty means the review amount above.",
    kind: "amount",
  },
  {
    key: "always_refund_under",
    label: "Refund ceiling doesn't apply under",
    description:
      "For disputes under this amount, Settle may refund past the ceiling. Confidence still applies.",
    kind: "amount",
  },
];

/** The form's values: text as typed, so an empty field can mean "use the default". */
export type PolicyFormValues = { rules_text: string } & Record<LimitKey, string>;

function limitField(kind: LimitDefinition["kind"]) {
  return z
    .string()
    .trim()
    .superRefine((value, context) => {
      if (value === "") return;
      const number = Number(value);
      const problem = !/^\d+(\.\d+)?$/.test(value)
        ? "Enter a number, like 150 or 99.50."
        : kind === "percent" && number > 100
          ? "Enter a percentage from 0 to 100."
          : !/^\d+(\.\d{1,2})?$/.test(value)
            ? "Use at most two decimal places."
            : null;
      if (problem) context.addIssue({ code: "custom", message: problem });
    });
}

export const policySchema = z.object({
  rules_text: z
    .string()
    .max(RULES_MAX, `Keep your rules under ${RULES_MAX.toLocaleString("en-US")} characters.`),
  ...(Object.fromEntries(LIMITS.map(({ key, kind }) => [key, limitField(kind)])) as Record<
    LimitKey,
    ReturnType<typeof limitField>
  >),
});

const KIND = Object.fromEntries(LIMITS.map(({ key, kind }) => [key, kind])) as Record<
  LimitKey,
  LimitDefinition["kind"]
>;

/** Confidence is stored from 0 to 1 and edited as a percentage. */
function toField(key: LimitKey, value: number | null | undefined) {
  if (value == null) return "";
  return KIND[key] === "percent" ? String(Math.round(value * 1000) / 10) : String(value);
}

function fromField(key: LimitKey, value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const number = Number(trimmed);
  return KIND[key] === "percent" ? Math.round(number * 10) / 1000 : number;
}

export function toFormValues(policy: Policy | null): PolicyFormValues {
  const values = { rules_text: policy?.rules_text ?? "" } as PolicyFormValues;
  for (const { key } of LIMITS) values[key] = toField(key, policy?.[key]);
  return values;
}

export function toPolicyUpdate(values: PolicyFormValues): Required<PolicyUpdate> {
  const update = { rules_text: values.rules_text.trim() } as Required<PolicyUpdate>;
  for (const { key } of LIMITS) update[key] = fromField(key, values[key]);
  return update;
}

export interface EffectiveLimits {
  confidence: number;
  reviewAmount: number;
  refundCeiling: number;
  acceptMax: number;
  refundAnyUnder: number;
}

/** The limits that would apply: each set value, or the default. Invalid input counts as unset. */
export function effectiveLimits(values: PolicyFormValues): EffectiveLimits {
  const valid = (key: LimitKey) => {
    const parsed = policySchema.shape[key].safeParse(values[key]);
    return parsed.success ? fromField(key, values[key]) : null;
  };
  const reviewAmount = valid("human_in_loop_amount") ?? DEFAULT_LIMITS.human_in_loop_amount;
  return {
    confidence: valid("confidence_threshold") ?? DEFAULT_LIMITS.confidence_threshold,
    reviewAmount,
    refundCeiling: valid("partial_refund_ceiling") ?? DEFAULT_LIMITS.partial_refund_ceiling,
    acceptMax: valid("auto_accept_max") ?? reviewAmount,
    refundAnyUnder: valid("always_refund_under") ?? DEFAULT_LIMITS.always_refund_under,
  };
}

const amount = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
export const formatAmount = (value: number) => amount.format(value);
export const formatPercent = (value: number) => `${Math.round(value * 1000) / 10}%`;

export interface PolicySummary {
  /** When Settle acts without you, one condition per line. */
  rules: string[];
  /** Combinations that don't do what they seem to. */
  warnings: string[];
}

/** What a set of limits means in practice, in the order the backend checks them. */
export function summarize(limits: EffectiveLimits): PolicySummary {
  const { confidence, reviewAmount, refundCeiling, acceptMax, refundAnyUnder } = limits;
  const rules = [
    `It is at least ${formatPercent(confidence)} confident in its decision.`,
    `The dispute is for less than ${formatAmount(reviewAmount)}.`,
    refundAnyUnder > 0
      ? `A refund is at most ${formatAmount(refundCeiling)}, or the dispute is under ${formatAmount(refundAnyUnder)}.`
      : `A refund is at most ${formatAmount(refundCeiling)}.`,
    `Accepting the buyer's claim is for at most ${formatAmount(acceptMax)}.`,
  ];

  const warnings: string[] = [];
  if (confidence === 0) {
    warnings.push("At 0% confidence, Settle acts on every decision, however unsure it is.");
  }
  if (refundCeiling >= reviewAmount) {
    warnings.push(
      `The refund limit has no effect: disputes of ${formatAmount(reviewAmount)} or more already come to you.`,
    );
  }
  if (acceptMax > reviewAmount) {
    warnings.push(
      `The accept limit has no effect above ${formatAmount(reviewAmount)}, where every dispute comes to you.`,
    );
  }
  if (refundAnyUnder > 0 && refundAnyUnder > refundCeiling && refundAnyUnder <= reviewAmount) {
    warnings.push(
      `Disputes under ${formatAmount(refundAnyUnder)} can be refunded in full without you, past the ${formatAmount(refundCeiling)} refund limit.`,
    );
  }
  return { rules, warnings };
}
