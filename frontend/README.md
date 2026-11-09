# Settle frontend

The seller console for Settle: sign in, review disputes, watch the mediator reason live, approve or
reject escalations, read the audit trail and set the fairness policy. It talks to the FastAPI
backend in `../backend` over REST and one WebSocket (see `../UI_INTEGRATION.md`).

## Stack

| Concern              | Choice                                                         |
| -------------------- | -------------------------------------------------------------- |
| Build                | Vite, React 19, TypeScript (strict)                            |
| Routing              | TanStack Router, file-based (`src/routes`)                     |
| Server state         | TanStack Query                                                 |
| Live mediation state | Zustand store fed by the mediation WebSocket                   |
| API types            | `openapi-typescript` + `openapi-fetch`, generated from the API |
| UI                   | Tailwind CSS v4, shadcn/ui (Radix), lucide icons               |
| Forms                | React Hook Form + Zod                                          |
| Tests                | Vitest, Testing Library, MSW; Playwright and axe end to end    |

## Getting started

Requires Node 22+ and pnpm.

```bash
pnpm install
pnpm dev            # http://localhost:5173
```

The dev server proxies `/api` (REST and the WebSocket) to `http://localhost:8000`, so run the
backend there (see `../backend/README.md`) or point `BACKEND_URL` somewhere else in `.env.local`.
With `DISPUTE_SOURCE_MODE=fixture` on the backend, the seeded disputes drive the whole flow with no
PayPal credentials. Mediations need AWS credentials for Bedrock in `backend/.env`; without them,
every run fails at the reasoning step.

## Scripts

| Script           | What it does                                             |
| ---------------- | -------------------------------------------------------- |
| `pnpm dev`       | Dev server with hot reload                               |
| `pnpm build`     | Type-check, then production build into `dist/`           |
| `pnpm preview`   | Serve the production build locally                       |
| `pnpm typecheck` | TypeScript only                                          |
| `pnpm lint`      | ESLint (type-aware, React, hooks, a11y, TanStack rules)  |
| `pnpm format`    | Prettier, including Tailwind class ordering              |
| `pnpm test`      | Vitest once; `pnpm test:watch` to keep it running        |
| `pnpm e2e`       | Playwright end to end against the real backend           |
| `pnpm gen:api`   | Regenerate API types from the running backend's OpenAPI  |
| `pnpm check`     | Typecheck, lint, format check and tests: run before a PR |

## End-to-end tests

`pnpm e2e` runs Playwright against the production build and the real backend. It needs the
backend's Python environment (`uv sync` in `../backend`) and a browser:

```bash
pnpm exec playwright install chromium   # once; or set E2E_BROWSER_CHANNEL=chrome
pnpm e2e
```

Playwright starts two servers on ports of their own, so your dev servers and database are never
touched:

- `e2e/backend.py` on port 8100 runs the backend app on a throwaway SQLite database with the demo
  disputes, and a scripted model in place of Bedrock, so nothing calls AWS or PayPal. The model is
  swapped through the backend's container, as its own tests do; nothing in `../backend` changes.
  Under the default limits its scripts end each demo case a known way: the earbuds refund comes to
  the seller (74% confident), the shirt is replaced as a dry run, and the 500 charge is escalated
  with no outcome. Each test clears the database first through `POST /__e2e__/reset`, which only
  this server has.
- `vite preview` on port 5174 serves the build and proxies `/api` to it.

The specs cover sign-in, the cases list, mediating, approving and rejecting, the audit trail and
the fairness policy. `accessibility.spec.ts` checks every page against WCAG 2.1 AA with axe, in
light and dark mode, and for sideways scrolling at phone width. A failure leaves a trace in
`test-results/`; open it with `pnpm exec playwright show-trace <path>`.

If the backend changes what its model streams (`stream_agentic` in its Bedrock model), update
`ScriptedModel` in `e2e/backend.py` to match.

| Variable                           | Default                       | Purpose                                    |
| ---------------------------------- | ----------------------------- | ------------------------------------------ |
| `BACKEND_PYTHON`                   | `../backend/.venv/bin/python` | A Python with the backend's dependencies   |
| `E2E_BROWSER_CHANNEL`              | Playwright's Chromium         | `chrome` to use an installed Google Chrome |
| `E2E_BACKEND_PORT`, `E2E_WEB_PORT` | `8100`, `5174`                | Ports for the two servers                  |

## API types

`src/lib/api/schema.d.ts` is generated; never edit it by hand. After any backend API change:

```bash
pnpm gen:api                         # from http://localhost:8000/openapi.json
pnpm gen:api path/to/openapi.json    # or from a saved schema
```

Then call the typed client through `unwrap` (or `unwrapPage` for lists), which returns the
envelope's `data` or throws an `ApiError`:

```ts
import { api } from "@/lib/api/client";
import { unwrap, unwrapPage } from "@/lib/api/envelope";

const user = await unwrap(api.GET("/api/v1/auth/me"));
const { items, meta } = await unwrapPage(
  api.GET("/api/v1/disputes", { params: { query: { page: 1 } } }),
);
```

The WebSocket contract is not in OpenAPI, so its events are typed by hand in
`src/features/mediation/events.ts`. Keep that file in step with the backend's `src/api/ws/events.py`.

## Conventions

- **Errors.** Every failed call is an `ApiError` with the backend's `code`, `message`, field errors
  and `requestId` (the `X-Request-ID`). Queries show errors where their data would be. Failed
  mutations raise a toast with the request ID automatically; set `meta: { silentError: true }`
  when the component shows the error itself, and use `applyServerFieldErrors` (`src/lib/forms.ts`)
  to put the backend's 422 field errors on the matching inputs.
- **Retries.** Queries retry network and server errors, never a 4xx.
- **Session.** `src/lib/session.ts` holds the JWT and its expiry in localStorage, shared by every
  tab. The token is in localStorage rather than a cookie because the mediation WebSocket needs it
  in the query string. The backend issues 30-minute tokens with no refresh, so the app warns two
  minutes before expiry and then returns to sign-in with an explanation. A 401 on any request that
  carried a token ends the session the same way.
- **Access.** Every signed-in screen is a child of `src/routes/_app.tsx`, whose `beforeLoad` is the
  one place access is checked. Add new screens under `src/routes/_app/`.
- **Live mediation.** One WebSocket per tab, opened by the signed-in layout and closed on
  sign-out. `src/features/mediation/client.ts` is the only way to use it: `mediate`, plus the
  header's connection status. Its state lives in `useMediationStore`, one `Run` per dispute. The
  socket reconnects with backoff, pings to catch dead connections, refetches server data after an
  outage, and ends the session when the server refuses the token (close codes 4401 and 4402).
  - Every event names its dispute, so several runs can stream at once. `mediate` refuses only a
    second run of the same dispute while one is under way.
  - `case.error` always ends what it names. A run the server never starts fails after 15 seconds.
  - Nothing is queued: with the socket down, `mediate` says so instead of sending later.
- **Approve and reject** go over REST (`reviewDispute` in `src/features/disputes/api.ts`), not
  the socket, so each gets its answer. The backend refuses a second action on a case with a 409.
  When no answer comes, the case page says the action may or may not have happened and asks the
  seller to check before trying again.
- **Cases.** The cases list merges three sources by PayPal dispute id: `/disputes/open` (PayPal's
  disputes plus the demo ones), `/disputes` (what Settle has recorded, loaded in full), and the
  runs in `useMediationStore`. `src/features/disputes/cases.ts` works out each case's status as a
  pure, tested function:
  - Settle's record beats the open list's status.
  - A run this tab saw change since the lists were last fetched beats the record, until the
    refetch that follows every finished run catches up.
  - A record still "mediating" after 10 minutes is shown as unfinished: a server restart mid-run
    leaves it that way.

  The case page (`src/features/disputes/case-detail.ts`) follows the same rule, and keeps a
  finished run on show while the record agrees with how it ended, so a failure's reason stays
  visible. Dispute queries live under `disputeKeys.all` (`["disputes"]`), which the mediation
  client invalidates whenever a case settles. The list's filter and search are kept in the
  address.

- **Model text.** The mediator writes light Markdown. Show it with `ModelText`
  (`src/features/disputes/model-text.tsx`), which formats bold, italics, code and lists as React
  elements and never as HTML.
- **Fairness policy.** `src/features/policy/` edits the seller's rules and five limits over
  `GET` and `PUT /policy`. The form edits text so an empty limit can mean "use the default"; it
  sends every limit on save, `null` for the default, so clearing a field resets it. Confidence is
  stored from 0 to 1 and edited as a percentage. `DEFAULT_LIMITS` in `policy-model.ts` mirrors the
  backend's `guardrails.py`; keep the two in step. The page explains what the limits mean in
  practice, warns about combinations that have no effect, and asks before leaving unsaved changes.
- **Audit trail.** `src/features/audit/` pages through `GET /audit` 25 rows at a time, with the
  gate, outcome and page in the address bar so a filtered view can be shared. The rows are lean,
  so `resultOf` in `entries.ts` reads a dry run or a failed execution the way the backend's
  `executor.py` writes them; keep the two in step. Opening a row (`?entry=<id>`) shows the full
  entry beside the list, from the dispute's trail (`GET /audit/dispute/{id}`). The backend
  records no entry for a rejection, or for approving an escalation with no outcome, so neither
  appears here.
- **Times.** Read backend timestamps with `parseServerTime` (`src/lib/format.ts`). Some arrive
  without an offset, and those are UTC, not local time.
- **Theme.** `src/lib/theme.ts` (light, dark or system), applied before first paint by the script
  in `index.html`.

## Layout

```
src/
  app/            providers, router, query client, devtools
  routes/         file-based routes; thin, they compose features
  features/       one folder per area (audit, auth, disputes, mediation, policy)
  components/ui/  shadcn primitives (added with the shadcn CLI, then owned here)
  components/     shared app components
  lib/api/        generated schema, typed client, envelope helpers, ApiError
  lib/            session, theme, forms, format, notify, env, utils
  hooks/          shared React hooks
  styles/         globals.css: Tailwind and the design tokens (light and dark)
  test/           test setup, MSW server, render helpers
e2e/              Playwright specs, their fixtures, and the e2e backend (backend.py)
```

`src/routeTree.gen.ts` is generated by the router plugin on `dev` and `build`.

## Adding UI primitives

```bash
pnpm dlx shadcn@latest add button dialog table
```

Components land in `src/components/ui` and are ours to edit. Colour comes from the tokens in
`src/styles/globals.css`: neutral by default, with `success`, `warning`, `info` and `destructive`
reserved for meaning. Text on a pale tint of one uses its `-strong` shade (`text-warning-strong`),
which stays readable in light mode.

## Environment

| Variable       | Used by          | Default                 | Purpose                                          |
| -------------- | ---------------- | ----------------------- | ------------------------------------------------ |
| `BACKEND_URL`  | `vite.config.ts` | `http://localhost:8000` | Where the dev proxy sends `/api`                 |
| `VITE_API_URL` | the app          | same origin             | API origin for a build served apart from the API |

When the app and the API are on different origins, the backend's `CORS_ORIGINS` must include the
app's origin.
