import createClient, { type Middleware } from "openapi-fetch";

import { env } from "@/lib/env";
import { endSession, getActiveSession } from "@/lib/session";

import type { paths } from "./schema";

const AUTHORIZATION = "Authorization";

const auth: Middleware = {
  onRequest({ request }) {
    const session = getActiveSession();
    if (session) request.headers.set(AUTHORIZATION, `Bearer ${session.accessToken}`);
    return request;
  },
  onResponse({ request, response }) {
    // A token the backend no longer accepts means the session is over. A 401 on a request without
    // one (wrong password at sign-in) is an ordinary error for the caller to show.
    if (response.status === 401 && request.headers.has(AUTHORIZATION)) endSession("expired");
    return response;
  },
};

/**
 * Typed REST client for the backend. Paths and payloads come from `pnpm gen:api`; wrap calls in
 * `unwrap` / `unwrapPage` from `./envelope` to get the payload or an `ApiError`.
 */
export const api = createClient<paths>({
  baseUrl: env.apiUrl,
  // Look fetch up per call instead of capturing it at import, so test interceptors see every request.
  fetch: (request) => globalThis.fetch(request),
});

api.use(auth);
