import { http, HttpResponse } from "msw";

import type { AuditEntry, DisputePreview, DisputeRecord, OpenDispute } from "@/lib/api/types";
import { envelope, errorEnvelope } from "@/test/fixtures";

interface Disputes {
  open?: OpenDispute[];
  records?: DisputeRecord[];
  /** Case files the preview endpoint can assemble, by PayPal id. */
  previews?: Record<string, DisputePreview["case_file"]>;
  /** Audit entries, newest first, by PayPal id. */
  trails?: Record<string, AuditEntry[]>;
}

const notFound = () =>
  HttpResponse.json(errorEnvelope("DISPUTE_NOT_FOUND", "Dispute not found"), { status: 404 });

/**
 * The dispute endpoints, served the way the backend does: the open list all at once, the records a
 * page at a time, one record by either of its ids (404 for one Settle hasn't seen), a preview, and
 * a record's trail. Every test gets empty lists; `server.use(...disputeHandlers({...}))` fills them.
 */
export function disputeHandlers({
  open = [],
  records = [],
  previews = {},
  trails = {},
}: Disputes = {}) {
  const find = (id: string) =>
    records.find((record) => record.paypal_dispute_id === id || record.id === id);

  return [
    // Before the single-dispute route, which would otherwise take "open" for an id.
    http.get("*/api/v1/disputes/open", () => HttpResponse.json(envelope(open))),

    http.get("*/api/v1/disputes", ({ request }) => {
      const params = new URL(request.url).searchParams;
      const page = Number(params.get("page") ?? 1);
      const pageSize = Number(params.get("page_size") ?? 20);
      const items = records.slice((page - 1) * pageSize, page * pageSize);
      return HttpResponse.json(
        envelope(items, {
          page,
          page_size: pageSize,
          total: records.length,
          total_pages: Math.ceil(records.length / pageSize),
        }),
      );
    }),

    http.get("*/api/v1/disputes/:id/preview", ({ params }) => {
      const id = String(params.id);
      const caseFile = previews[id];
      if (!caseFile) {
        return HttpResponse.json(errorEnvelope("COMMON_INTERNAL_ERROR", "Unknown dispute"), {
          status: 500,
        });
      }
      return HttpResponse.json(
        envelope({ dispute_id: id, status: find(id)?.status ?? "open", case_file: caseFile }),
      );
    }),

    http.get("*/api/v1/disputes/:id", ({ params }) => {
      const record = find(String(params.id));
      return record ? HttpResponse.json(envelope(record)) : notFound();
    }),

    http.get("*/api/v1/audit/dispute/:id", ({ params }) => {
      const record = find(String(params.id));
      if (!record) return notFound();
      return HttpResponse.json(envelope(trails[record.paypal_dispute_id] ?? []));
    }),
  ];
}
