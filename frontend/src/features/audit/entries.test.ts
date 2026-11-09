import { describe, expect, it } from "vitest";

import { actionText } from "@/features/disputes/labels";

import { resultOf, whatHappened } from "./entries";

/** The backend writes an em dash into some of its action text. */
const DASH = "\u2014";

const ESCALATED = {
  gate: "escalate",
  executed: false,
  action_taken: "Escalated to the seller",
  engine: "llm_tools",
};

describe("what came of a decision", () => {
  it("tells carried out, dry run, escalated and failed apart", () => {
    expect(
      resultOf({ ...ESCALATED, gate: "execute", executed: true, action_taken: "Issued refund" }),
    ).toBe("carried_out");
    expect(resultOf({ ...ESCALATED, gate: "execute", action_taken: "Issued refund" })).toBe(
      "dry_run",
    );
    expect(resultOf(ESCALATED)).toBe("sent_to_you");
    expect(resultOf({ ...ESCALATED, action_taken: `Execution failed ${DASH} escalated` })).toBe(
      "failed",
    );
  });

  it("says in one line what reached PayPal", () => {
    expect(whatHappened(ESCALATED)).toBe("Nothing sent to PayPal");
    expect(
      whatHappened({
        ...ESCALATED,
        gate: "execute",
        action_taken: `Offered a replacement to the buyer (dry run ${DASH} no live capture)`,
      }),
    ).toBe("Offered a replacement to the buyer");
    expect(
      whatHappened({
        ...ESCALATED,
        gate: "execute",
        executed: true,
        engine: "approved",
        action_taken: "Issued refund of 59.99 USD",
      }),
    ).toBe("Approved by you · Issued refund of 59.99 USD");
  });
});

describe("the backend's action text", () => {
  it("drops the dry-run note, which shows as a badge", () => {
    expect(actionText(`Issued refund of 59.99 USD (dry run ${DASH} no live capture)`)).toBe(
      "Issued refund of 59.99 USD",
    );
    expect(actionText("Issued refund of 59.99 USD")).toBe("Issued refund of 59.99 USD");
    expect(actionText("  ")).toBeNull();
    expect(actionText(null)).toBeNull();
  });
});
