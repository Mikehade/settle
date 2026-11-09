import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = env.BACKEND_URL || "http://localhost:8000";

  return {
    plugins: [
      // Must run before the React plugin so generated route files are transformed too.
      tanstackRouter({ target: "react", autoCodeSplitting: true }),
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: { "@": path.resolve(import.meta.dirname, "src") },
    },
    server: {
      port: 5173,
      strictPort: true,
      // Same-origin in development: REST and the mediation WebSocket both go through
      // this proxy, so the backend needs no CORS settings for local work.
      proxy: {
        "/api": { target: backendUrl, changeOrigin: true, ws: true },
      },
    },
    test: {
      environment: "jsdom",
      // Playwright runs the end-to-end specs in e2e/.
      include: ["src/**/*.test.{ts,tsx}"],
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
    },
  };
});
