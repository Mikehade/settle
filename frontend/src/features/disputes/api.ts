import { queryOptions } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap, unwrapPage } from "@/lib/api/envelope";
import { isApiError } from "@/lib/api/errors";
import type { DisputeRecord } from "@/lib/api/types";

/**
 * Query keys for dispute data. The mediation client invalidates everything under `all` whenever a
 * case settles, so every list and detail view refreshes without knowing about the socket.
 */
export const disputeKeys = {
  all: ["disputes"] as const,
  open: () => [...disputeKeys.all, "open"] as const,
  records: () => [...disputeKeys.all, "records"] as const,
  detail: (id: string) => [...disputeKeys.all, "detail", id] as const,
  preview: (id: string) => [...disputeKeys.all, "preview", id] as const,
  trail: (id: string) => [...disputeKeys.all, "trail", id] as const,
};

/** Disputes open in PayPal, plus the seeded demo ones. The backend sends them all at once. */
export function openDisputesQuery() {
  return queryOptions({
    queryKey: disputeKeys.open(),
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/disputes/open", { signal })),
  });
}

/** The backend's largest page. */
const PAGE_SIZE = 100;
/** Enough for any seller's history; past this, the list says it is showing the latest cases. */
const MAX_PAGES = 10;

export interface DisputeRecords {
  items: DisputeRecord[];
  /** How many the backend has, which is more than `items` holds when the history is very long. */
  total: number;
}

/**
 * Every dispute Settle has recorded for the seller, newest first. The cases list merges these with
 * the open disputes and the live runs, which no single request can do, so it loads them all.
 */
export function disputeRecordsQuery() {
  return queryOptions({
    queryKey: disputeKeys.records(),
    queryFn: async ({ signal }): Promise<DisputeRecords> => {
      const page = (number: number) =>
        unwrapPage(
          api.GET("/api/v1/disputes", {
            params: { query: { page: number, page_size: PAGE_SIZE } },
            signal,
          }),
        );

      const first = await page(1);
      const last = Math.min(first.meta.totalPages, MAX_PAGES);
      const rest = await Promise.all(
        Array.from({ length: Math.max(0, last - 1) }, (_, index) => page(index + 2)),
      );
      return {
        items: [first, ...rest].flatMap((result) => result.items),
        total: first.meta.total,
      };
    },
  });
}

/** `null` where the backend answers 404: Settle has no record of the dispute, or it isn't yours. */
async function orNull<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (isApiError(error) && error.status === 404) return null;
    throw error;
  }
}

/** Settle's record of a dispute, by its PayPal id. `null` until Settle has mediated it. */
export function disputeQuery(id: string) {
  return queryOptions({
    queryKey: disputeKeys.detail(id),
    queryFn: ({ signal }) =>
      orNull(
        unwrap(
          api.GET("/api/v1/disputes/{dispute_id}", {
            params: { path: { dispute_id: id } },
            signal,
          }),
        ),
      ),
  });
}

/** The case file for a dispute Settle hasn't mediated, assembled without mediating it. */
export function disputePreviewQuery(id: string) {
  return queryOptions({
    queryKey: disputeKeys.preview(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/disputes/{paypal_dispute_id}/preview", {
          params: { path: { paypal_dispute_id: id } },
          signal,
        }),
      ),
  });
}

/** Every decision made on a dispute, newest first. Empty until Settle has mediated it. */
export function disputeTrailQuery(id: string) {
  return queryOptions({
    queryKey: disputeKeys.trail(id),
    queryFn: async ({ signal }) =>
      (await orNull(
        unwrap(
          api.GET("/api/v1/audit/dispute/{dispute_id}", {
            params: { path: { dispute_id: id } },
            signal,
          }),
        ),
      )) ?? [],
  });
}

export type ReviewAction = "approve" | "reject";

/**
 * Approves or rejects an escalated recommendation. Over REST rather than the socket because each
 * request gets its answer: the result, or an error saying why not (409 when the case was already
 * acted on, which is also what stops a second approval refunding twice).
 */
export function reviewDispute(id: string, action: ReviewAction) {
  const params = { params: { path: { paypal_dispute_id: id } } };
  return unwrap(
    action === "approve"
      ? api.POST("/api/v1/disputes/{paypal_dispute_id}/approve", params)
      : api.POST("/api/v1/disputes/{paypal_dispute_id}/reject", params),
  );
}
