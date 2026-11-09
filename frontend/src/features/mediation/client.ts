import { env } from "@/lib/env";
import { endSession, getActiveSession } from "@/lib/session";

import type { ServerEvent } from "./events";
import { type ConnectionStatus, MediationSocket, type MediationSocketOptions } from "./socket";
import {
  applyServerEvent,
  failRun,
  initialMediationState,
  isFinished,
  markDropped,
  type MediationState,
  requestRun,
  useMediationStore,
} from "./store";

export type SendResult<Reason extends string> = { ok: true } | { ok: false; reason: Reason };

export interface MediationClientOptions {
  /**
   * How long the server may take to start a requested mediation. It runs one mediation per
   * dispute at a time and queues a second request silently, so silence is the only sign.
   */
  startTimeoutMs?: number;
  socket?: Partial<Pick<MediationSocketOptions, "pingIntervalMs" | "backoff" | "WebSocket">>;
}

export const NOT_STARTED_MESSAGE = "Settle didn't start mediating this case. Try again.";

const MEDIATION_PATH = "/api/v1/ws/mediation";

/** The socket address for a token. Browsers can't set headers on a WebSocket, so it rides along. */
export function mediationUrl(token: string) {
  const url = new URL(MEDIATION_PATH, env.apiUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token);
  return url.toString();
}

export function createMediationClient(options: MediationClientOptions = {}) {
  const { startTimeoutMs = 15_000 } = options;

  const store = useMediationStore;
  const update = (change: (state: MediationState) => MediationState) =>
    store.setState(change(store.getState()), true);

  const startTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const settledListeners = new Set<() => void>();

  const settled = () => settledListeners.forEach((listener) => listener());

  function clearStartTimer(disputeId: string) {
    clearTimeout(startTimers.get(disputeId));
    startTimers.delete(disputeId);
  }

  function onEvent(event: ServerEvent) {
    const before = store.getState();
    update((state) => applyServerEvent(state, event));
    const after = store.getState();

    // A requested run the server picked up, or refused, no longer needs its start timeout.
    for (const disputeId of startTimers.keys()) {
      if (after.runs[disputeId]?.status !== "requested") clearStartTimer(disputeId);
    }

    // Server data changes when a run ends, and when another client approves or rejects a case
    // (an executed or explained event that belongs to no run here, so the state is unchanged).
    const ended = event.event === "case.explained" || event.event === "case.error";
    const elsewhere = event.event === "case.executed" && after === before;
    if (ended || elsewhere) settled();
  }

  let lastState: ConnectionStatus["state"] = "idle";
  function onStatus(connection: ConnectionStatus) {
    store.setState({ connection });
    // Back after an outage: whatever ended meanwhile was missed, so refetch.
    if (connection.state === "open" && lastState === "reconnecting") settled();
    lastState = connection.state;
  }

  const socket = new MediationSocket({
    ...options.socket,
    url: () => {
      const session = getActiveSession();
      return session ? mediationUrl(session.accessToken) : null;
    },
    onEvent,
    onStatus,
    onRejected: () => endSession("expired"),
    onDropped: () => update(markDropped),
  });

  return {
    /** Opens the socket for the signed-in seller and keeps it open. */
    connect: () => socket.start(),

    /** Closes the socket and forgets every run. For leaving the signed-in app. */
    disconnect() {
      socket.stop();
      startTimers.forEach(clearTimeout);
      startTimers.clear();
      store.setState(initialMediationState, true);
    },

    retryNow: () => socket.retryNow(),

    /**
     * Asks the server to mediate one dispute and stream the run here. Refused while a run of the
     * same dispute is under way; the server would queue the second and run it straight after.
     */
    mediate(disputeId: string): SendResult<"offline" | "running"> {
      if (!isFinished(store.getState().runs[disputeId])) return { ok: false, reason: "running" };
      if (!socket.send({ event: "seller.mediate", data: { dispute_id: disputeId } })) {
        return { ok: false, reason: "offline" };
      }

      update((state) => requestRun(state, disputeId));
      clearStartTimer(disputeId);
      startTimers.set(
        disputeId,
        setTimeout(() => {
          startTimers.delete(disputeId);
          update((state) => failRun(state, disputeId, NOT_STARTED_MESSAGE));
          settled();
        }, startTimeoutMs),
      );
      return { ok: true };
    },

    /** Called whenever server data may have changed: a run ended, or the socket came back. */
    onSettled(listener: () => void) {
      settledListeners.add(listener);
      return () => {
        settledListeners.delete(listener);
      };
    },
  };
}

export type MediationClient = ReturnType<typeof createMediationClient>;

/** The app's one mediation client. */
export const mediation = createMediationClient();
