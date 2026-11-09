import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import { useEffect } from "react";
import { toast } from "sonner";

import { endSession, useSession } from "@/lib/session";

const WARNING_BEFORE_MS = 2 * 60_000;

/**
 * Runs inside the signed-in layout. Warns shortly before the token runs out (the backend has no
 * refresh), ends the session when it does, and sends the user to sign-in whenever the session
 * ends for any reason: expiry, sign-out, a rejected token, or another tab signing out.
 */
export function useSessionLifecycle() {
  const session = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!session) return;
    const remaining = session.expiresAt - Date.now();
    const timers = [setTimeout(() => endSession("expired"), Math.max(remaining, 0))];

    if (remaining > WARNING_BEFORE_MS) {
      timers.push(
        setTimeout(() => {
          toast.warning("Your session ends in 2 minutes", {
            description: "Finish what you're doing; you'll need to sign in again after that.",
            duration: WARNING_BEFORE_MS,
          });
        }, remaining - WARNING_BEFORE_MS),
      );
    }
    return () => timers.forEach(clearTimeout);
  }, [session]);

  useEffect(() => {
    if (session) return;
    // Re-running the route guard redirects to sign-in. The cache is dropped once the signed-in
    // screens are gone, so nothing refetches without a token on the way out.
    void router.invalidate().then(() => queryClient.clear());
  }, [session, router, queryClient]);
}
