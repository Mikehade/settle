import { describe, expect, it } from "vitest";

import { formatMoney, formatRelative, parseServerTime } from "./format";

describe("parseServerTime", () => {
  it("reads a timestamp without an offset as UTC, the way the backend writes it", () => {
    expect(parseServerTime("2026-11-05T14:49:36")).toBe(Date.UTC(2026, 10, 5, 14, 49, 36));
    expect(parseServerTime("2026-11-05T14:49:36.554649")).toBe(
      Date.UTC(2026, 10, 5, 14, 49, 36, 554),
    );
  });

  it("keeps an offset when there is one", () => {
    expect(parseServerTime("2026-11-05T14:49:36Z")).toBe(Date.UTC(2026, 10, 5, 14, 49, 36));
    expect(parseServerTime("2026-11-05T14:49:36+01:00")).toBe(Date.UTC(2026, 10, 5, 13, 49, 36));
  });

  it("gives null for nothing, or for something that isn't a time", () => {
    expect(parseServerTime(null)).toBeNull();
    expect(parseServerTime("")).toBeNull();
    expect(parseServerTime("yesterday")).toBeNull();
  });
});

describe("formatMoney", () => {
  it("formats known currencies, and falls back to the code for anything else", () => {
    expect(formatMoney(59.99, "USD")).toBe("$59.99");
    expect(formatMoney(12, "EUR")).toBe("€12.00");
    expect(formatMoney(5, "nope")).toBe("5.00 nope");
  });
});

describe("formatRelative", () => {
  const now = Date.UTC(2026, 10, 5, 12, 0, 0);
  const ago = (ms: number) => formatRelative(now - ms, now);
  const MINUTE = 60_000;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;

  it("counts up from just now to days", () => {
    expect(ago(10_000)).toBe("just now");
    expect(ago(5 * MINUTE)).toBe("5 minutes ago");
    expect(ago(3 * HOUR)).toBe("3 hours ago");
    expect(ago(DAY)).toBe("yesterday");
    expect(ago(3 * DAY)).toBe("3 days ago");
  });

  it("switches to a date after a week, with the year once it is a different one", () => {
    expect(ago(20 * DAY)).toBe("Oct 16");
    expect(ago(365 * DAY)).toBe("Nov 5, 2025");
  });
});
