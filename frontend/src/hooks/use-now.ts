import { useSyncExternalStore } from "react";

const TICK_MS = 30_000;

let now = Date.now();
let timer: ReturnType<typeof setInterval> | undefined;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((notify) => notify());
    }, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) clearInterval(timer);
  };
}

/**
 * The current time, refreshed every 30 seconds, for "5 minutes ago" labels and anything else that
 * goes stale with time. One shared clock for every component that asks.
 */
export function useNow() {
  return useSyncExternalStore(subscribe, () => now);
}
