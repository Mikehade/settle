import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import type { Gate, Outcome } from "@/features/mediation/events";
import { api } from "@/lib/api/client";
import { unwrapPage } from "@/lib/api/envelope";

export const AUDIT_PAGE_SIZE = 25;

/** What the backend can narrow the trail by, and which page of it. */
export interface AuditFilters {
  gate?: Gate;
  outcome?: Outcome;
  page?: number;
}

/**
 * Query keys for the audit list. The mediation client and the approve and reject actions
 * invalidate everything under `all`, so the list picks up each new decision by itself.
 */
export const auditKeys = {
  all: ["audit"] as const,
  page: (filters: AuditFilters) => [...auditKeys.all, "page", filters] as const,
};

/**
 * One page of the seller's decisions, newest first. The rows are lean: the case file and PayPal's
 * reply come with a dispute's full trail. The page on show stays up while the next one loads.
 */
export function auditPageQuery({ gate, outcome, page = 1 }: AuditFilters) {
  return queryOptions({
    queryKey: auditKeys.page({ gate, outcome, page }),
    queryFn: ({ signal }) =>
      unwrapPage(
        api.GET("/api/v1/audit", {
          params: { query: { gate, outcome, page, page_size: AUDIT_PAGE_SIZE } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
