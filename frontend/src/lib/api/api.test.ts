import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { startSession, useSessionStore } from "@/lib/session";
import { envelope, errorEnvelope, TEST_USER } from "@/test/fixtures";
import { server } from "@/test/msw/server";

import { api } from "./client";
import { unwrap, unwrapPage } from "./envelope";
import { ApiError } from "./errors";

const token = { access_token: "abc", expires_in: 1800 };

describe("unwrap", () => {
  it("returns the payload inside the envelope", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(envelope(TEST_USER))));

    await expect(unwrap(api.GET("/api/v1/auth/me"))).resolves.toEqual(TEST_USER);
  });

  it("turns an error envelope into an ApiError with code, message, field errors and request ID", async () => {
    server.use(
      http.put("*/api/v1/policy", () =>
        HttpResponse.json(
          errorEnvelope("COMMON_VALIDATION_ERROR", "Validation error", [
            { field: "body.confidence_threshold", message: "Must be at most 1" },
          ]),
          { status: 422, headers: { "X-Request-ID": "req-123" } },
        ),
      ),
    );

    const error = await unwrap(api.PUT("/api/v1/policy", { body: {} })).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "COMMON_VALIDATION_ERROR",
      message: "Validation error",
      requestId: "req-123",
      fieldErrors: [{ field: "body.confidence_threshold", message: "Must be at most 1" }],
      isRetryable: false,
    });
  });

  it("falls back to the envelope's request ID when the header is missing", async () => {
    server.use(
      http.get("*/api/v1/policy", () =>
        HttpResponse.json(errorEnvelope("POLICY_NOT_FOUND", "No fairness policy set yet"), {
          status: 404,
        }),
      ),
    );

    await expect(unwrap(api.GET("/api/v1/policy"))).rejects.toMatchObject({
      code: "POLICY_NOT_FOUND",
      requestId: "req-test",
    });
  });

  it("reports an unreachable server as a retryable NETWORK_ERROR", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.error()));

    await expect(unwrap(api.GET("/api/v1/auth/me"))).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
      isRetryable: true,
    });
  });
});

describe("unwrapPage", () => {
  it("returns the items with the pagination from meta", async () => {
    server.use(
      http.get("*/api/v1/audit", () =>
        HttpResponse.json(envelope([], { page: 2, page_size: 20, total: 41, total_pages: 3 })),
      ),
    );

    await expect(
      unwrapPage(api.GET("/api/v1/audit", { params: { query: { page: 2 } } })),
    ).resolves.toEqual({ items: [], meta: { page: 2, pageSize: 20, total: 41, totalPages: 3 } });
  });
});

describe("auth middleware", () => {
  it("sends the session token as a bearer header", async () => {
    startSession(token);
    let authorization: string | null = null;
    server.use(
      http.get("*/api/v1/auth/me", ({ request }) => {
        authorization = request.headers.get("Authorization");
        return HttpResponse.json(envelope(TEST_USER));
      }),
    );

    await unwrap(api.GET("/api/v1/auth/me"));

    expect(authorization).toBe("Bearer abc");
  });

  it("ends the session as expired when the backend rejects the token", async () => {
    startSession(token);
    server.use(
      http.get("*/api/v1/auth/me", () =>
        HttpResponse.json(errorEnvelope("AUTH_TOKEN_EXPIRED", "Token expired"), { status: 401 }),
      ),
    );

    await expect(unwrap(api.GET("/api/v1/auth/me"))).rejects.toMatchObject({ status: 401 });

    expect(useSessionStore.getState()).toMatchObject({ session: null, endReason: "expired" });
  });

  it("leaves things alone on a 401 for a request sent without a token", async () => {
    await expect(
      unwrap(api.POST("/api/v1/auth/login", { body: { email: "x@y.test", password: "nope" } })),
    ).rejects.toMatchObject({ code: "AUTH_INVALID_CREDENTIALS" });

    expect(useSessionStore.getState().endReason).toBeNull();
  });
});
