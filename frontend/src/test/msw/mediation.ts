import { ws } from "msw";

import { CLOSE_INVALID_TOKEN, type ClientEvent } from "@/features/mediation/events";
import { frame, type ScriptedEvent, TEST_TOKEN } from "@/test/fixtures";

const link = ws.link("ws://*/api/v1/ws/mediation");

type Reply = (...events: ScriptedEvent[]) => void;
type MessageHandler = (message: ClientEvent, reply: Reply) => void;

let refuseWith: number | null = null;
let onMessage: MessageHandler | null = null;
const received: ClientEvent[] = [];

/**
 * A fake mediation socket that behaves like the backend: it checks the token, says
 * `connection.ready`, answers `ping`, and hands every other message to the test.
 */
export const mediationBackend = {
  handler: link.addEventListener("connection", ({ client }) => {
    if (client.url.searchParams.get("token") !== TEST_TOKEN) {
      client.close(CLOSE_INVALID_TOKEN, "Invalid token");
      return;
    }
    if (refuseWith !== null) {
      client.close(refuseWith);
      return;
    }

    const reply: Reply = (...events) =>
      events.forEach(([event, data]) => client.send(frame(event, data)));
    reply(["connection.ready", { channel: "mediation:test" }]);

    client.addEventListener("message", ({ data }) => {
      if (typeof data !== "string") throw new Error("The app sends text frames only");
      const message = JSON.parse(data) as ClientEvent;
      received.push(message);
      if (message.event === "ping") reply(["agent.typing", { typing: false }]);
      else onMessage?.(message, reply);
    });
  }),

  /** Messages the app sent, pings included. */
  received,

  /** Close every new connection with this code instead of accepting it. */
  refuseWith(code: number | null) {
    refuseWith = code;
  },

  /** Answer the app's messages (other than `ping`). */
  onMessage(handler: MessageHandler) {
    onMessage = handler;
  },

  /** Send events to every open connection, as a run started elsewhere would. */
  broadcast(...events: ScriptedEvent[]) {
    events.forEach(([event, data]) => link.broadcast(frame(event, data)));
  },

  /** Drop every open connection, as a server restart would. */
  dropAll(code = 1012) {
    link.clients.forEach((client) => client.close(code));
  },

  reset() {
    refuseWith = null;
    onMessage = null;
    received.length = 0;
  },
};
