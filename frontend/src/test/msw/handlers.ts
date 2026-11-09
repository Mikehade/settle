import { http, HttpResponse } from "msw";

import { envelope, errorEnvelope, TEST_PASSWORD, TEST_TOKEN, TEST_USER } from "@/test/fixtures";

import { auditListHandler } from "./audit";
import { disputeHandlers } from "./disputes";
import { mediationBackend } from "./mediation";

/**
 * A minimal backend that every test gets: health, sign-in for the test user, `/auth/me` for the
 * test token, empty dispute lists, an empty audit trail, no fairness policy, and the mediation
 * socket. Tests override any of these with `server.use(...)`, and script the socket through
 * `mediationBackend`.
 */
export const defaultHandlers = [
  http.get("*/api/v1/health", () => HttpResponse.json(envelope({ alive: true }))),

  http.post("*/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (body.email === TEST_USER.email && body.password === TEST_PASSWORD) {
      return HttpResponse.json(
        envelope({ access_token: TEST_TOKEN, token_type: "bearer", expires_in: 1800 }),
      );
    }
    return HttpResponse.json(
      errorEnvelope("AUTH_INVALID_CREDENTIALS", "Invalid email or password"),
      { status: 401 },
    );
  }),

  http.get("*/api/v1/auth/me", ({ request }) => {
    if (request.headers.get("Authorization") === `Bearer ${TEST_TOKEN}`) {
      return HttpResponse.json(envelope(TEST_USER));
    }
    return HttpResponse.json(errorEnvelope("AUTH_TOKEN_INVALID", "Invalid token"), {
      status: 401,
    });
  }),

  ...disputeHandlers(),
  // Only the list: a dispute's trail comes from `disputeHandlers`, which knows its records.
  auditListHandler(),

  // No policy saved. A test that saves one serves its own with `policyBackend()`, so nothing it
  // saves can leak into the next test.
  http.get("*/api/v1/policy", () =>
    HttpResponse.json(errorEnvelope("POLICY_NOT_FOUND", "No fairness policy set yet"), {
      status: 404,
    }),
  ),

  mediationBackend.handler,
];
