import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

/**
 * The signed-in session: the backend's JWT and when it stops being valid.
 *
 * It lives in localStorage because the mediation WebSocket needs the raw token in its query
 * string (browsers cannot set socket headers), so an httpOnly cookie would not help, and so every
 * tab shares one sign-in. The backend issues short-lived tokens with no refresh, so a session ends
 * at `expiresAt` and the user signs in again.
 */
export interface Session {
  accessToken: string;
  expiresAt: number;
}

/** Why the last session ended; the sign-in page explains an expiry. */
export type SessionEndReason = "expired" | "signed-out";

interface SessionState {
  session: Session | null;
  endReason: SessionEndReason | null;
}

const STORAGE_KEY = "settle-session";

export const useSessionStore = create<SessionState>()(
  persist((): SessionState => ({ session: null, endReason: null }), {
    name: STORAGE_KEY,
    storage: createJSONStorage(() => localStorage),
    partialize: (state) => ({ session: state.session }),
  }),
);

export function startSession(
  token: { access_token: string; expires_in: number },
  now = Date.now(),
): Session {
  const session = { accessToken: token.access_token, expiresAt: now + token.expires_in * 1000 };
  useSessionStore.setState({ session, endReason: null });
  return session;
}

export function endSession(reason: SessionEndReason) {
  if (useSessionStore.getState().session === null) return;
  useSessionStore.setState({ session: null, endReason: reason });
}

export function isExpired(session: Session, now = Date.now()) {
  return session.expiresAt <= now;
}

/** The current session if it is still valid; an expired one is ended on the way out. */
export function getActiveSession(now = Date.now()): Session | null {
  const { session } = useSessionStore.getState();
  if (session && isExpired(session, now)) {
    endSession("expired");
    return null;
  }
  return session;
}

export function useSession() {
  return useSessionStore((state) => state.session);
}

/** Keeps tabs in step: signing in or out in one tab applies to the others. */
export function syncSessionAcrossTabs() {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) void useSessionStore.persist.rehydrate();
  };
  window.addEventListener("storage", onStorage);
  return () => window.removeEventListener("storage", onStorage);
}
