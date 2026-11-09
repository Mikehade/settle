/**
 * Formatting for numbers, money and times. The interface is written in English, so these follow
 * en-US rather than the browser's locale; mixing the two would read oddly.
 */
const LOCALE = "en-US";

const HAS_OFFSET = /(?:z|[+-]\d{2}:?\d{2})$/i;

/**
 * A backend timestamp as epoch milliseconds, or `null` when it is missing or unreadable. Some
 * timestamps arrive without an offset (the database drops it); the backend writes them in UTC.
 */
export function parseServerTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(HAS_OFFSET.test(value) ? value : `${value}Z`);
  return Number.isNaN(ms) ? null : ms;
}

const moneyFormats = new Map<string, Intl.NumberFormat>();

/** "$59.99". Falls back to "59.99 XYZ" for a currency code the browser doesn't know. */
export function formatMoney(amount: number, currency: string) {
  let format = moneyFormats.get(currency);
  if (!format) {
    try {
      format = new Intl.NumberFormat(LOCALE, { style: "currency", currency });
    } catch {
      return `${amount.toFixed(2)} ${currency}`;
    }
    moneyFormats.set(currency, format);
  }
  return format.format(amount);
}

const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
const sameYearDate = new Intl.DateTimeFormat(LOCALE, { month: "short", day: "numeric" });
const fullDate = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium" });
const dateTime = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * "just now", "5 minutes ago", "yesterday", then a plain date once it is more than a week old,
 * where a relative time stops being useful.
 */
export function formatRelative(ms: number, now: number) {
  const elapsed = now - ms;
  if (Math.abs(elapsed) < MINUTE) return "just now";
  if (Math.abs(elapsed) < HOUR) return relative.format(-Math.round(elapsed / MINUTE), "minute");
  if (Math.abs(elapsed) < DAY) return relative.format(-Math.round(elapsed / HOUR), "hour");
  if (Math.abs(elapsed) < 7 * DAY) return relative.format(-Math.round(elapsed / DAY), "day");
  const sameYear = new Date(ms).getFullYear() === new Date(now).getFullYear();
  return (sameYear ? sameYearDate : fullDate).format(ms);
}

/** "Nov 5, 2026, 3:00 PM", for a tooltip or anywhere the exact time matters. */
export function formatDateTime(ms: number) {
  return dateTime.format(ms);
}
