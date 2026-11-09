import { describe, expect, it } from "vitest";

import type { Policy } from "@/lib/api/types";

import {
  effectiveLimits,
  type PolicyFormValues,
  policySchema,
  summarize,
  toFormValues,
  toPolicyUpdate,
} from "./policy-model";

const SAVED: Policy = {
  id: "p-1",
  seller_id: "s-1",
  rules_text: "Refund in full when nothing shipped.",
  confidence_threshold: 0.925,
  human_in_loop_amount: 300,
  partial_refund_ceiling: null,
  auto_accept_max: 50,
  always_refund_under: null,
  created_at: "2026-11-09T09:00:00",
  updated_at: "2026-11-09T09:00:00",
};

const empty = (overrides: Partial<PolicyFormValues> = {}): PolicyFormValues => ({
  ...toFormValues(null),
  ...overrides,
});

describe("moving between the form and the API", () => {
  it("edits confidence as a percentage and leaves unset limits empty", () => {
    expect(toFormValues(SAVED)).toEqual({
      rules_text: "Refund in full when nothing shipped.",
      confidence_threshold: "92.5",
      human_in_loop_amount: "300",
      partial_refund_ceiling: "",
      auto_accept_max: "50",
      always_refund_under: "",
    });
  });

  it("sends every limit, null where the seller wants the default", () => {
    expect(toPolicyUpdate(toFormValues(SAVED))).toEqual({
      rules_text: "Refund in full when nothing shipped.",
      confidence_threshold: 0.925,
      human_in_loop_amount: 300,
      partial_refund_ceiling: null,
      auto_accept_max: 50,
      always_refund_under: null,
    });
  });
});

describe("checking the form", () => {
  const error = (values: Partial<PolicyFormValues>) => {
    const result = policySchema.safeParse(empty(values));
    return result.success ? null : result.error.issues[0]?.message;
  };

  it("accepts empty limits, whole numbers and two decimal places", () => {
    expect(error({ human_in_loop_amount: " 99.50 ", confidence_threshold: "80" })).toBeNull();
  });

  it("explains what's wrong with a value", () => {
    expect(error({ human_in_loop_amount: "abc" })).toBe("Enter a number, like 150 or 99.50.");
    expect(error({ partial_refund_ceiling: "-5" })).toBe("Enter a number, like 150 or 99.50.");
    expect(error({ confidence_threshold: "120" })).toBe("Enter a percentage from 0 to 100.");
    expect(error({ auto_accept_max: "10.555" })).toBe("Use at most two decimal places.");
    expect(error({ rules_text: "x".repeat(4001) })).toBe("Keep your rules under 4,000 characters.");
  });
});

describe("explaining a policy", () => {
  it("lists the default limits in the order the backend checks them", () => {
    expect(summarize(effectiveLimits(empty())).rules).toEqual([
      "It is at least 80% confident in its decision.",
      "The dispute is for less than 200.",
      "A refund is at most 150.",
      "Accepting the buyer's claim is for at most 200.",
    ]);
    expect(summarize(effectiveLimits(empty())).warnings).toEqual([]);
  });

  it("ignores a value that isn't valid yet, rather than guessing at it", () => {
    expect(effectiveLimits(empty({ human_in_loop_amount: "12a" })).reviewAmount).toBe(200);
  });

  it("warns about limits that don't do what they seem to", () => {
    const { warnings } = summarize(
      effectiveLimits(
        empty({
          confidence_threshold: "0",
          human_in_loop_amount: "100",
          auto_accept_max: "500",
          always_refund_under: "",
        }),
      ),
    );

    expect(warnings).toEqual([
      "At 0% confidence, Settle acts on every decision, however unsure it is.",
      "The refund limit has no effect: disputes of 100 or more already come to you.",
      "The accept limit has no effect above 100, where every dispute comes to you.",
    ]);
  });

  it("says when small disputes can be refunded past the refund limit", () => {
    const summary = summarize(
      effectiveLimits(empty({ partial_refund_ceiling: "20", always_refund_under: "50" })),
    );

    expect(summary.rules[2]).toBe("A refund is at most 20, or the dispute is under 50.");
    expect(summary.warnings).toEqual([
      "Disputes under 50 can be refunded in full without you, past the 20 refund limit.",
    ]);
  });
});
