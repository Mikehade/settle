import { setupServer } from "msw/node";

import { defaultHandlers } from "./handlers";

/**
 * One network interceptor for the whole test run (HTTP and WebSocket). Tests add handlers with
 * `server.use(...)`; they are reset to the defaults after each test, and any unhandled request
 * fails the test.
 */
export const server = setupServer(...defaultHandlers);
