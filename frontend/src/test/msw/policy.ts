import { http, HttpResponse } from "msw";

import type { Policy, PolicyUpdate } from "@/lib/api/types";
import { envelope, errorEnvelope, TEST_USER } from "@/test/fixtures";

/**
 * The policy endpoints, keeping whatever is saved: 404 until the first save, like the backend.
 * `saved` lists every body sent, for tests to check what went over the wire.
 */
export function policyBackend(initial: Policy | null = null) {
  let policy = initial;
  const saved: PolicyUpdate[] = [];

  const handlers = [
    http.get("*/api/v1/policy", () =>
      policy
        ? HttpResponse.json(envelope(policy))
        : HttpResponse.json(errorEnvelope("POLICY_NOT_FOUND", "No fairness policy set yet"), {
            status: 404,
          }),
    ),
    http.put("*/api/v1/policy", async ({ request }) => {
      const body = (await request.json()) as PolicyUpdate;
      saved.push(body);
      const now = new Date().toISOString();
      policy = {
        id: policy?.id ?? "policy-1",
        seller_id: TEST_USER.id,
        rules_text: body.rules_text ?? policy?.rules_text ?? "",
        confidence_threshold: body.confidence_threshold ?? null,
        human_in_loop_amount: body.human_in_loop_amount ?? null,
        partial_refund_ceiling: body.partial_refund_ceiling ?? null,
        auto_accept_max: body.auto_accept_max ?? null,
        always_refund_under: body.always_refund_under ?? null,
        created_at: policy?.created_at ?? now,
        updated_at: now,
      };
      return HttpResponse.json(envelope(policy));
    }),
  ];

  return { handlers, saved };
}
