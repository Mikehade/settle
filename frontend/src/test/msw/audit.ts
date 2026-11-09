import { http, HttpResponse } from "msw";

import type { AuditEntry, AuditListItem } from "@/lib/api/types";
import { envelope, errorEnvelope } from "@/test/fixtures";

/** A list row, as the backend trims an entry for the list. */
function toListItem({
  case_file: _caseFile,
  paypal_result: _paypalResult,
  seller_id: _sellerId,
  decision: _decision,
  ...row
}: AuditEntry): AuditListItem {
  return row;
}

/** The audit list over entries given newest first, a page at a time, by gate and outcome. */
export function auditListHandler(entries: AuditEntry[] = []) {
  return http.get("*/api/v1/audit", ({ request }) => {
    const params = new URL(request.url).searchParams;
    const gate = params.get("gate");
    const outcome = params.get("outcome");
    const page = Number(params.get("page") ?? 1);
    const pageSize = Number(params.get("page_size") ?? 20);
    const matching = entries.filter(
      (entry) => (!gate || entry.gate === gate) && (!outcome || entry.outcome === outcome),
    );
    return HttpResponse.json(
      envelope(matching.slice((page - 1) * pageSize, page * pageSize).map(toListItem), {
        page,
        page_size: pageSize,
        total: matching.length,
        total_pages: Math.ceil(matching.length / pageSize),
      }),
    );
  });
}

/**
 * The audit endpoints over one set of entries: the list, and each dispute's full trail (404 for a
 * dispute with no entries, as the backend answers for one Settle hasn't recorded).
 */
export function auditHandlers(entries: AuditEntry[] = []) {
  return [
    auditListHandler(entries),
    http.get("*/api/v1/audit/dispute/:id", ({ params }) => {
      const trail = entries.filter((entry) => entry.paypal_dispute_id === params.id);
      if (trail.length === 0) {
        return HttpResponse.json(errorEnvelope("DISPUTE_NOT_FOUND", "Dispute not found"), {
          status: 404,
        });
      }
      return HttpResponse.json(envelope(trail));
    }),
  ];
}
