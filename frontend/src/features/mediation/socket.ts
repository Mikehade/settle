import {
  CLOSE_INVALID_TOKEN,
  CLOSE_NOT_AUTHENTICATED,
  type ClientEvent,
  parseServerEvent,
  type ServerEvent,
} from "./events";

export type ConnectionState = "idle" | "connecting" | "open" | "reconnecting";

export interface ConnectionStatus {
  /**
   * `open` means the server has sent `connection.ready`, not just that the socket opened: the
   * server accepts first and checks the token afterwards.
   */
  state: ConnectionState;
  /** Failed attempts since the last good connection. */
  attempt: number;
  /** When the next attempt starts, while waiting to reconnect. */
  retryAt: number | null;
}

export const IDLE: ConnectionStatus = { state: "idle", attempt: 0, retryAt: null };

export interface MediationSocketOptions {
  /** The address to connect to, with the token. `null` means signed out: stay idle. */
  url: () => string | null;
  onEvent: (event: ServerEvent) => void;
  onStatus: (status: ConnectionStatus) => void;
  /** The server refused the token. The socket stops; signing in again is the only way back. */
  onRejected: (code: number) => void;
  /** An open connection was lost. A reconnect is already scheduled. */
  onDropped?: () => void;
  /** How often to check the connection is alive. Defaults to 20 seconds. */
  pingIntervalMs?: number;
  /** Reconnect delays double from `baseMs` up to `maxMs`, with jitter. */
  backoff?: { baseMs: number; maxMs: number };
  /** For tests. */
  WebSocket?: typeof WebSocket;
  random?: () => number;
}

const SOCKET_CONNECTING = 0;
const CLOSE_NORMAL = 1000;
const CLOSE_KEEPALIVE_TIMEOUT = 4000;

/**
 * The one mediation socket for this tab. Reconnects with exponential backoff until stopped, checks
 * the connection with `ping` (the server answers every ping), and gives up only when the server
 * refuses the token. It never queues: sending while not connected returns `false`, so nothing
 * that moves money is replayed later behind the seller's back.
 */
export class MediationSocket {
  readonly #options: MediationSocketOptions;
  #ws: WebSocket | null = null;
  #status: ConnectionStatus = IDLE;
  #wanted = false;
  #awaitingPong = false;
  #retryTimer: ReturnType<typeof setTimeout> | undefined;
  #pingTimer: ReturnType<typeof setInterval> | undefined;

  constructor(options: MediationSocketOptions) {
    this.#options = options;
  }

  get status() {
    return this.#status;
  }

  /** Connects, and keeps the connection up until `stop()`. */
  start() {
    if (this.#wanted) return;
    this.#wanted = true;
    window.addEventListener("online", this.#wake);
    document.addEventListener("visibilitychange", this.#wake);
    this.#connect();
  }

  stop() {
    this.#wanted = false;
    window.removeEventListener("online", this.#wake);
    document.removeEventListener("visibilitychange", this.#wake);
    clearTimeout(this.#retryTimer);
    this.#teardown();
    this.#setStatus(IDLE);
  }

  /** Skips the wait before the next reconnect attempt. */
  retryNow() {
    if (!this.#wanted || this.#status.retryAt === null) return;
    clearTimeout(this.#retryTimer);
    this.#connect();
  }

  /** Sends one event if the connection is up. Returns whether it was sent. */
  send(event: ClientEvent) {
    if (this.#status.state !== "open" || !this.#ws) return false;
    this.#ws.send(JSON.stringify(event));
    return true;
  }

  #connect() {
    const url = this.#options.url();
    if (!url) {
      this.stop();
      return;
    }

    const Socket = this.#options.WebSocket ?? globalThis.WebSocket;
    const ws = new Socket(url);
    this.#ws = ws;
    this.#setStatus({
      state: this.#status.attempt === 0 ? "connecting" : "reconnecting",
      attempt: this.#status.attempt,
      retryAt: null,
    });

    ws.onmessage = (message: MessageEvent) => {
      this.#awaitingPong = false;
      const event = parseServerEvent(message.data);
      if (!event) return;
      if (event.event === "connection.ready") {
        this.#setStatus({ state: "open", attempt: 0, retryAt: null });
        this.#startKeepAlive();
      }
      this.#options.onEvent(event);
    };

    ws.onclose = (close: CloseEvent) => {
      const wasOpen = this.#status.state === "open";
      this.#detach(ws);
      this.#ws = null;
      this.#stopKeepAlive();

      if (close.code === CLOSE_NOT_AUTHENTICATED || close.code === CLOSE_INVALID_TOKEN) {
        this.stop();
        this.#options.onRejected(close.code);
        return;
      }
      if (wasOpen) this.#options.onDropped?.();
      this.#scheduleReconnect();
    };
  }

  #scheduleReconnect() {
    if (!this.#wanted) return;
    const attempt = this.#status.attempt + 1;
    const { baseMs, maxMs } = this.#options.backoff ?? { baseMs: 1_000, maxMs: 30_000 };
    const random = this.#options.random ?? Math.random;
    // Full delay at most, half at least, so tabs that lost the server together don't return
    // together.
    const delay = Math.min(maxMs, baseMs * 2 ** (attempt - 1)) * (0.5 + random() / 2);

    this.#setStatus({ state: "reconnecting", attempt, retryAt: Date.now() + delay });
    this.#retryTimer = setTimeout(() => this.#connect(), delay);
  }

  #startKeepAlive() {
    this.#stopKeepAlive();
    this.#awaitingPong = false;
    this.#pingTimer = setInterval(() => {
      // Nothing at all since the last ping, not even its answer: the connection is gone even if
      // the browser has not noticed yet.
      if (this.#awaitingPong) {
        this.#teardown(CLOSE_KEEPALIVE_TIMEOUT);
        this.#stopKeepAlive();
        this.#options.onDropped?.();
        this.#scheduleReconnect();
        return;
      }
      this.#awaitingPong = true;
      this.send({ event: "ping", data: {} });
    }, this.#options.pingIntervalMs ?? 20_000);
  }

  #stopKeepAlive() {
    clearInterval(this.#pingTimer);
    this.#pingTimer = undefined;
  }

  /** Closes the current socket without reacting to its close event. */
  #teardown(code = CLOSE_NORMAL) {
    const ws = this.#ws;
    this.#ws = null;
    this.#stopKeepAlive();
    if (!ws) return;
    this.#detach(ws);
    // Closing a socket that is still connecting makes the browser log a warning; let it open
    // first, then close it.
    if (ws.readyState === SOCKET_CONNECTING) ws.onopen = () => ws.close(code);
    else ws.close(code);
  }

  #detach(ws: WebSocket) {
    ws.onopen = null;
    ws.onmessage = null;
    ws.onclose = null;
  }

  #wake = () => {
    if (document.visibilityState === "visible") this.retryNow();
  };

  #setStatus(status: ConnectionStatus) {
    const current = this.#status;
    if (
      current.state === status.state &&
      current.attempt === status.attempt &&
      current.retryAt === status.retryAt
    ) {
      return;
    }
    this.#status = status;
    this.#options.onStatus(status);
  }
}
