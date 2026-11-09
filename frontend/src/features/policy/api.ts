import { queryOptions } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/envelope";
import { isApiError } from "@/lib/api/errors";
import type { PolicyUpdate } from "@/lib/api/types";

export const policyKeys = {
  all: ["policy"] as const,
};

/** The seller's fairness policy, or `null` before they have saved one. */
export function policyQuery() {
  return queryOptions({
    queryKey: policyKeys.all,
    queryFn: async ({ signal }) => {
      try {
        return await unwrap(api.GET("/api/v1/policy", { signal }));
      } catch (error) {
        if (isApiError(error) && error.code === "POLICY_NOT_FOUND") return null;
        throw error;
      }
    },
  });
}

/**
 * Saves the whole policy. Every limit is sent, `null` where the seller wants the default, so a
 * cleared field goes back to the default rather than keeping its old value.
 */
export function savePolicy(policy: Required<PolicyUpdate>) {
  return unwrap(api.PUT("/api/v1/policy", { body: policy }));
}
