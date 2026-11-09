import { describe, expect, it } from "vitest";

import { setTheme } from "./theme";

describe("setTheme", () => {
  it("applies and remembers an explicit choice", () => {
    setTheme("dark");

    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("settle-theme")).toBe("dark");
  });

  it("follows the system for 'system' and forgets the saved choice", () => {
    setTheme("dark");
    setTheme("system");

    // The test environment reports a light system preference.
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("settle-theme")).toBeNull();
  });
});
