import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { frame } from "@/test/fixtures";

import { CLOSE_INVALID_TOKEN, type ServerEvent } from "./events";
import { type ConnectionStatus, MediationSocket, type MediationSocketOptions } from "./socket";

/** Just enough of a browser WebSocket for the client, plus controls for the server's side. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static latest() {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("No socket was opened");
    return socket;
  }

  readonly url: string;
  readyState = 0;
  sent: unknown[] = [];
  closedWith: number | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((close: { code: number }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(JSON.parse(data));
  }

  close(code = 1000) {
    this.readyState = 3;
    this.closedWith = code;
  }

  // The server's side.
  accept() {
    this.readyState = 1;
    this.onopen?.();
    this.onmessage?.({ data: frame("connection.ready", { channel: "mediation:test" }) });
  }

  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function setup(overrides: Partial<MediationSocketOptions> = {}) {
  const events: ServerEvent[] = [];
  const statuses: ConnectionStatus[] = [];
  const onRejected = vi.fn();
  const onDropped = vi.fn();
  const socket = new MediationSocket({
    url: () => "ws://settle.test/api/v1/ws/mediation?token=t",
    onEvent: (event) => events.push(event),
    onStatus: (status) => statuses.push(status),
    onRejected,
    onDropped,
    pingIntervalMs: 1_000,
    backoff: { baseMs: 100, maxMs: 1_000 },
    random: () => 1,
    WebSocket: FakeWebSocket as unknown as typeof WebSocket,
    ...overrides,
  });
  return { socket, events, statuses, onRejected, onDropped };
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.instances = [];
});

afterEach(() => {
  vi.useRealTimers();
});

describe("MediationSocket", () => {
  it("counts as open only once the server says the connection is ready", () => {
    const { socket, events } = setup();

    socket.start();
    expect(socket.status.state).toBe("connecting");
    expect(FakeWebSocket.latest().url).toContain("token=t");

    FakeWebSocket.latest().accept();
    expect(socket.status).toEqual({ state: "open", attempt: 0, retryAt: null });
    expect(events.map((event) => event.event)).toEqual(["connection.ready"]);
  });

  it("stays idle with no session to connect with", () => {
    const { socket } = setup({ url: () => null });

    socket.start();

    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(socket.status.state).toBe("idle");
  });

  it("reconnects with growing delays, and starts over after a good connection", () => {
    const { socket, onDropped } = setup();
    socket.start();
    FakeWebSocket.latest().accept();

    FakeWebSocket.latest().drop();
    expect(onDropped).toHaveBeenCalledOnce();
    expect(socket.status).toMatchObject({ state: "reconnecting", attempt: 1 });

    vi.advanceTimersByTime(99);
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    // The server is still down: the next wait is twice as long.
    FakeWebSocket.latest().drop();
    expect(socket.status).toMatchObject({ state: "reconnecting", attempt: 2 });
    vi.advanceTimersByTime(199);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    FakeWebSocket.latest().accept();

    expect(socket.status).toEqual({ state: "open", attempt: 0, retryAt: null });
    // A failed attempt before the socket was ever ready is not a dropped connection.
    expect(onDropped).toHaveBeenCalledOnce();
  });

  it("never waits longer than the cap", () => {
    const { socket } = setup();
    socket.start();

    for (let attempt = 1; attempt <= 6; attempt++) {
      FakeWebSocket.latest().drop();
      vi.advanceTimersByTime(1_000);
    }

    expect(FakeWebSocket.instances).toHaveLength(7);
  });

  it("retries at once when asked", () => {
    const { socket } = setup();
    socket.start();
    FakeWebSocket.latest().drop();

    socket.retryNow();

    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(socket.status).toMatchObject({ state: "reconnecting", retryAt: null });
  });

  it("gives up and reports it when the server refuses the token", () => {
    const { socket, onRejected } = setup();
    socket.start();
    FakeWebSocket.latest().accept();

    FakeWebSocket.latest().drop(CLOSE_INVALID_TOKEN);
    vi.advanceTimersByTime(10_000);

    expect(onRejected).toHaveBeenCalledWith(CLOSE_INVALID_TOKEN);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(socket.status.state).toBe("idle");
  });

  it("pings while open, and reconnects when nothing comes back", () => {
    const { socket, onDropped } = setup();
    socket.start();
    const first = FakeWebSocket.latest();
    first.accept();

    vi.advanceTimersByTime(1_000);
    expect(first.sent).toEqual([{ event: "ping", data: {} }]);

    // Any frame counts as an answer.
    first.onmessage?.({ data: frame("agent.typing", { typing: false }) });
    vi.advanceTimersByTime(1_000);
    expect(first.sent).toHaveLength(2);
    expect(socket.status.state).toBe("open");

    // Silence through a whole interval: the connection is dead.
    vi.advanceTimersByTime(1_000);
    expect(first.closedWith).toBe(4000);
    expect(onDropped).toHaveBeenCalledOnce();
    expect(socket.status.state).toBe("reconnecting");

    vi.advanceTimersByTime(100);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("sends only while open, and never queues", () => {
    const { socket } = setup();
    socket.start();

    expect(socket.send({ event: "seller.mediate", data: { dispute_id: "D-1" } })).toBe(false);

    FakeWebSocket.latest().accept();
    expect(socket.send({ event: "seller.mediate", data: { dispute_id: "D-1" } })).toBe(true);
    expect(FakeWebSocket.latest().sent).toEqual([
      { event: "seller.mediate", data: { dispute_id: "D-1" } },
    ]);
  });

  it("stops for good, closing a socket that is still connecting only once it opens", () => {
    const { socket, statuses } = setup();
    socket.start();
    const connecting = FakeWebSocket.latest();

    socket.stop();
    expect(connecting.closedWith).toBeNull();
    connecting.onopen?.();
    expect(connecting.closedWith).toBe(1000);

    vi.advanceTimersByTime(10_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(statuses.at(-1)?.state).toBe("idle");
  });

  it("ignores frames it does not understand", () => {
    const { socket, events } = setup();
    socket.start();
    const ws = FakeWebSocket.latest();
    ws.accept();

    ws.onmessage?.({ data: "not json" });
    ws.onmessage?.({ data: JSON.stringify({ event: "case.unknown", data: {} }) });
    ws.onmessage?.({ data: JSON.stringify({ event: "case.token", data: "text" }) });

    expect(events).toHaveLength(1);
  });
});
