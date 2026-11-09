import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { initialMediationState, useMediationStore } from "@/features/mediation/store";
import { useSessionStore } from "@/lib/session";

import { mediationBackend } from "./msw/mediation";
import { server } from "./msw/server";

// Whole-app tests load each route's code on first visit, which is slow while every test file runs
// at once. The default one-second wait for `findBy` and `waitFor` is too tight for that.
configure({ asyncUtilTimeout: 5_000 });

// Browser APIs jsdom lacks but the UI (theme, sidebar, Radix menus, scroll restoration) touches.
// The test environment reports a light, desktop-width screen.
function stub(target: object, name: string, value: unknown) {
  if (Reflect.get(target, name) === undefined) {
    Object.defineProperty(target, name, { value, configurable: true });
  }
}

stub(window, "matchMedia", (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
}));
stub(
  globalThis,
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);
stub(Element.prototype, "scrollIntoView", () => {});
stub(Element.prototype, "hasPointerCapture", () => false);
stub(Element.prototype, "releasePointerCapture", () => {});
window.scrollTo = () => {};

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  mediationBackend.reset();
  localStorage.clear();
  useSessionStore.setState({ session: null, endReason: null });
  useMediationStore.setState(initialMediationState, true);
});

afterAll(() => server.close());
