import { defineConfig, devices } from "@playwright/test";

import { BACKEND_PORT, BACKEND_URL, SELLERS, WEB_PORT, WEB_URL } from "./e2e/support/env";

/** The backend's Python, with its dependencies installed (`uv sync` in ../backend makes this). */
const python = process.env.BACKEND_PYTHON ?? "../backend/.venv/bin/python";

/**
 * End-to-end tests: the production build in a real browser, against the real backend on a
 * throwaway database, with a scripted model in place of Bedrock (see `e2e/backend.py`).
 */
export default defineConfig({
  testDir: "e2e",
  // One backend serves every test, and each resets it first, so they take turns.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // E2E_BROWSER_CHANNEL=chrome uses an installed Chrome instead of Playwright's Chromium.
      use: { ...devices["Desktop Chrome"], channel: process.env.E2E_BROWSER_CHANNEL },
    },
  ],
  webServer: [
    {
      command: `"${python}" e2e/backend.py`,
      url: `${BACKEND_URL}/api/v1/health`,
      env: {
        E2E_BACKEND_PORT: String(BACKEND_PORT),
        E2E_SELLERS: JSON.stringify(SELLERS),
        PYTHONDONTWRITEBYTECODE: "1",
      },
      // A fresh database every run: never reuse a backend left over from another one.
      reuseExistingServer: false,
      // Stopped gently, so it deletes its database on the way out.
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
      timeout: 60_000,
    },
    {
      command: `pnpm exec vite build && pnpm exec vite preview --port ${WEB_PORT} --strictPort`,
      url: WEB_URL,
      // The preview server proxies /api the way the dev server does.
      env: { BACKEND_URL },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
