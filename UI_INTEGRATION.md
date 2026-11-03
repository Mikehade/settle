# Settle — UI Integration Guide

How the frontend (in `frontend/`) talks to the backend (in `backend/`): the REST
endpoints, the mediation WebSocket, every event on the wire, and the exact payload
shapes. All responses use one envelope; the WebSocket streams the mediator's live
reasoning so the UI can show it thinking.

- Base URL: `http://localhost:8000`
- API prefix: `/api/v1` (set by `API_PREFIX`)
- Interactive docs: `http://localhost:8000/docs`
- Auth: JWT bearer. `POST /api/v1/auth/login` → `data.access_token`. Send it as
  `Authorization: Bearer <token>` on REST, and as `?token=<token>` on the WebSocket
  (browsers can't set WebSocket headers).

---

## 1. Response envelope

Every REST response is the same shape:

```json
{ "status": "success|error", "code": "OK", "message": "...", "data": <any>, "errors": null, "meta": null }
```

Lists add pagination in `meta`: `{ "page", "page_size", "total", "total_pages" }`.
Errors set `status: "error"`, a stable `code` (e.g. `DISPUTE_NOT_FOUND`,
`AUTH_NOT_AUTHENTICATED`), and a human `message`; validation errors (422) list fields
in `errors`.

---

## 2. REST endpoints

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | `{ email, password }` | `{ access_token, token_type, expires_in }` |
| `GET`  | `/api/v1/auth/me` | — | current user |
| `GET`  | `/api/v1/disputes` | `?page&page_size` | this seller's disputes (paginated) |
| `GET`  | `/api/v1/disputes/open` | — | open disputes from the source (real + seeded) |
| `GET`  | `/api/v1/disputes/{id}` | — | one dispute (internal UUID) |
| `POST` | `/api/v1/disputes/{paypal_dispute_id}/mediate` | — | runs a full mediation, returns the summary (no live trace) |
| `GET`  | `/api/v1/policy` | — | the seller's fairness policy |
| `PUT`  | `/api/v1/policy` | policy fields (below) | upserts the policy |
| `GET`  | `/api/v1/audit` | `?page&page_size` | audit trail (all decisions) |
| `GET`  | `/api/v1/audit/dispute/{id}` | — | audit entries for one dispute |
| `POST` | `/api/v1/webhooks/paypal` | PayPal event | detect hook (autonomous path) |
| `WS`   | `/api/v1/ws/mediation?token=<jwt>` | — | **live reasoning stream** (below) |

**Fairness policy (`PUT /policy`)** — `rules_text` is fed to the mediator verbatim; the
numeric fields are the guardrail overrides the executor enforces (any left null fall back
to the server defaults):

```json
{
  "rules_text": "Always refund under $25. Replace before refunding. Never auto-accept over $200.",
  "confidence_threshold": 0.8,
  "human_in_loop_amount": 200.0,
  "partial_refund_ceiling": 150.0,
  "auto_accept_max": 200.0,
  "always_refund_under": 25.0
}
```

**Mediation summary (`POST /{id}/mediate`)** — use this for a simple request/response;
use the WebSocket when you want to show the reasoning live:

```json
{ "dispute_id": "FIXTURE-NR-001", "gate": "execute", "executed": true,
  "action_taken": "Issued refund of 59.99 USD (dry run — no live capture)",
  "rationale": "Tracking shows the item was never shipped...",
  "decision": { "outcome": "refund", "confidence": 0.95, "refund_amount": 59.99 } }
```

---

## 3. Mediation WebSocket

Connect: `ws://localhost:8000/api/v1/ws/mediation?token=<jwt>`. On connect the server
sends `connection.ready`. One socket per seller; every event is broadcast to all of that
seller's open connections (so a second tab follows along). Close codes: `4401` (no
token), `4402` (invalid token).

Every frame is an envelope:

```json
{ "event": "<name>", "message_id": "<uuid>", "data": { ... }, "timestamp": "2026-11-02T04:50:00Z" }
```

### 3a. Inbound (client → server) — `{ "event": ..., "data": { ... } }`

| event | data | effect |
|---|---|---|
| `seller.mediate` | `{ "dispute_id": "..." }` | start mediating; the trace streams back |
| `seller.approve` | `{ "dispute_id": "..." }` | perform an escalated recommendation (the human is the gate) |
| `seller.reject` | `{ "dispute_id": "..." }` | leave the dispute for manual handling |
| `seller.message` | `{ "text": "..." }` | chat lane: answer a mediator question |
| `seller.set_policy` | policy fields | update the fairness policy inline |
| `ping` | — | keep-alive |

### 3b. Outbound (server → client) — the live case trace, in order

| event | data | when |
|---|---|---|
| `connection.ready` | `{ channel }` | on connect |
| `case.detected` | `{ dispute_id }` | mediation started |
| `case.gathering` | `{ dispute_id, case_file? }` | pulling PayPal facts / case file assembled |
| `case.reasoning_step` | `{ stage, text }` | one per step — `stage` ∈ `classify | weigh | policy | choose` |
| `case.token` | `{ text }` | rationale text delta (append as it streams) |
| `case.tool_call` | `{ name, input }` | the model used a tool (e.g. `lookup_tracking`, `propose_refund`) |
| `case.tool_result` | `{ name, ok }` | a tool returned |
| `case.decision` | `{ decision }` | the gated decision (outcome, confidence, rationale, gate) |
| `case.escalated` | `{ recommendation, gate_reason, decision }` | needs the seller — show approve/reject |
| `case.executed` | `{ result, decision }` | money/offer moved (or dry-run); balance beat |
| `case.explained` | `{ rationale, action_taken, decision }` | closing neutral explanation |
| `case.error` | `{ error }` | something failed |
| `agent.message` | `{ message, ... }` | chat-lane reply / policy ack |
| `agent.typing` | `{ typing }` | typing indicator |

The `decision` object (also stored in the audit trail):

```json
{ "dispute_id": "FIXTURE-NR-001", "dispute_type": "not_received", "outcome": "refund",
  "refund_amount": 59.99, "confidence": 0.95,
  "classification": "...", "evidence_summary": "...", "policy_application": "...",
  "rationale": "...", "gate": "execute", "gate_reason": "Within guardrails.",
  "escalation_recommendation": null }
```

### 3c. Suggested UI flow

1. Seller opens the dashboard → `GET /disputes/open` to list cases; connect the WS.
2. Seller clicks a case → send `seller.mediate`.
3. Render `case.reasoning_step` as a stepper (Classify → Weigh → Policy → Choose), stream
   `case.token` into a "rationale" panel, show `case.tool_call` as "checking tracking…".
4. On `case.decision` + `case.executed`: show the outcome and, for the demo, the PayPal
   sandbox balance moving. On `case.escalated`: show the recommendation with **Approve** /
   **Reject** buttons wired to `seller.approve` / `seller.reject`.
5. The audit screen reads `GET /audit` — inputs, chain, confidence, and action per case.

---

## 4. Quick smoke test (no frontend)

```bash
# 1. log in (after createsuperuser), grab the token
curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | jq -r .data.access_token
# 2. list seeded open disputes
curl -s localhost:8000/api/v1/disputes/open -H "authorization: Bearer $TOKEN" | jq
# 3. mediate one (DISPUTE_SOURCE_MODE=fixture works with no PayPal creds)
curl -s -X POST localhost:8000/api/v1/disputes/FIXTURE-NR-001/mediate -H "authorization: Bearer $TOKEN" | jq
```

For the live trace, point any WebSocket client at `ws://localhost:8000/api/v1/ws/mediation?token=$TOKEN`
and send `{"event":"seller.mediate","data":{"dispute_id":"FIXTURE-NR-001"}}`.
