import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModelText } from "./model-text";
import { parseBlocks } from "./model-text-blocks";

describe("the mediator's text", () => {
  it("splits paragraphs and lists the way the model writes them", () => {
    const text =
      "  \nThe evidence shows:\n- A $500 gift card.\n- Delivered.\n\nKey point:\nIt is unclear.";

    expect(parseBlocks(text)).toEqual([
      { kind: "paragraph", lines: ["The evidence shows:"] },
      { kind: "list", items: ["A $500 gift card.", "Delivered."] },
      { kind: "paragraph", lines: ["Key point:", "It is unclear."] },
    ]);
  });

  it("formats bold, italic and code, and leaves anything else as text", () => {
    render(
      <ModelText
        text={
          'Classified as **unauthorized_or_other**; policy says *"escalate"*. Use `refund`. <b>raw</b> **open'
        }
      />,
    );

    expect(screen.getByText("unauthorized_or_other").tagName).toBe("STRONG");
    expect(screen.getByText('"escalate"').tagName).toBe("EM");
    expect(screen.getByText("refund").tagName).toBe("CODE");
    // Markup from the model is shown, never interpreted, and an unclosed marker stays as typed.
    expect(screen.getByText(/<b>raw<\/b> \*\*open/)).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });
});
