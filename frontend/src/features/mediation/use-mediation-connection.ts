import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { disputeKeys } from "@/features/disputes/api";
import { useSession } from "@/lib/session";

import { mediation } from "./client";

/**
 * Runs inside the signed-in layout: keeps the mediation socket open for the current token, and
 * refetches dispute and audit data whenever a run or a review finishes. Leaving the signed-in app,
 * or another tab signing in as someone else, closes the socket and forgets every run.
 */
export function useMediationConnection() {
  const token = useSession()?.accessToken;
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!token) return;
    mediation.connect();
    return () => mediation.disconnect();
  }, [token]);

  useEffect(
    () =>
      mediation.onSettled(() => {
        void queryClient.invalidateQueries({ queryKey: disputeKeys.all });
        void queryClient.invalidateQueries({ queryKey: ["audit"] });
      }),
    [queryClient],
  );
}
