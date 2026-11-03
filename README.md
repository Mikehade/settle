# Settle

**An autonomous AI mediator for PayPal disputes.** A buyer opens a dispute; Settle wakes
up, gathers every fact PayPal already holds, reasons over both sides against the seller's
fairness policy, and either resolves it through PayPal or escalates to the seller — in
under a minute, with the whole reasoning trace streamed live and a plain-language
explanation for both parties.

Built for the PayPal AI Hackathon. The AI **chooses**; PayPal **executes** — every money
movement crosses a PayPal API, behind guardrails the mediator cannot override.

```
settle/
├── backend/            FastAPI service (layered, DI, async SQLAlchemy) — the whole system
├── frontend/           (your UI goes here)
└── UI_INTEGRATION.md   REST + WebSocket contract for the frontend
```

## What it does

A dispute flows through five steps: **Detect** (webhook or poll) → **Gather** (dispute +
transaction + tracking + both messages, assembled into one case file) → **Reason** (a
fixed chain: classify → weigh evidence → apply policy → choose) → **Act / gate** (perform
or escalate, under guardrails) → **Explain** (neutral rationale + a full audit trail).

Scope: **3 dispute types** (not received / not as described / unauthorized-or-other) and
**3 outcomes** (refund full-or-partial / reship / accept the claim), plus escalation.

## Architecture (two established standards, fused)

Built on a layered FastAPI kit — `api → core → domain ← infrastructure`, one DI
container, repositories returning TypedDicts, a unit of work owning transactions, typed
errors → one envelope, and **import-linter contracts enforced** (`python manage.py lint`).
See `backend/docs/ARCHITECTURE.md`.

The AI "brain" lives under **`src/domain/core/`** (agents, tools, prompts, constants) and
depends only on domain interfaces — the Bedrock model, PayPal client and executor are
injected, so the layer contract holds. Note the two cores: `src/domain/core` is the brain;
`src/core` is the kit's use-case services (mediation, disputes, policy, audit).

- **Agents** (`src/domain/core/agents`): `MediatorAgent` runs on either engine — native
  **LLM + tools** on Bedrock Converse, or a **LangGraph** chain — selected by
  `MEDIATION_ENGINE_GRAPH`.
- **Tools** (`src/domain/core/tools`): classes whose `_methods` auto-generate Bedrock tool
  specs. The mediator's entire action surface is four `propose_*` tools — its safety
  boundary. They only record a proposal; they never move money.
- **Model** (`src/infrastructure/language_models/bedrock.py`): async Bedrock with a shared
  fallback chain (`src/domain/core/constants/model_registry.py`) and live streaming.
- **Executor** (`src/infrastructure/services/executor.py`): the only code that moves
  money. Enforces the guardrails (confidence floor, human-in-the-loop amount, partial-
  refund ceiling, amount validation) **before** any PayPal call.
- **Transport**: a WebSocket streams the reasoning trace + decision and takes the seller's
  approve/reject (see `UI_INTEGRATION.md`).

PayPal APIs used: **Customer Disputes v1** (list / show / make-offer / accept-claim),
**Payments v2** (show capture / refund), **Shipment Tracking v1** (tracking status).

## Quickstart

```bash
cd backend
uv sync                               # or: python -m venv .venv && pip install -r requirements-dev.txt
cp .env.example .env                  # set DATABASE_URL, SECRET_KEY, PAYPAL_*, AWS_*/BEDROCK_*
python manage.py makemigrations "init"   # a migration is already included; this is a no-op if unchanged
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver            # http://localhost:8000/docs
```

**Run with no PayPal/AWS creds:** set `DISPUTE_SOURCE_MODE=fixture` and the three seeded
disputes (`FIXTURE-NR-001`, `FIXTURE-NAD-001`, `FIXTURE-UNAUTH-001`) drive the whole flow
offline (refunds run as dry-runs). Add real sandbox credentials and a real `capture_id` to
move balance for real.

```bash
python manage.py lint     # ruff + import-linter (layer contracts) — must pass
pytest                    # 48 tests, offline (no AWS/PayPal/DB): guardrails, mediator, API, WebSocket
```

## Tools used (for the submission form)

PayPal **Customer Disputes API**, **Orders/Payments (Refunds) API**, and **Shipment
Tracking API** (sandbox), reached through a typed REST client. AI mediation via **AWS
Bedrock** (Claude / Nova through a shared fallback chain) on the **Bedrock Converse**
tool-use API, with an optional **LangGraph** engine. **FastAPI** backend (async
SQLAlchemy 2.0, dependency-injector, Alembic); WebSocket for the live reasoning trace.

## License

MIT — see [LICENSE](LICENSE).
