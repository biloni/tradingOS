# Security

## Secrets handling

- All secrets (Alpaca keys, Anthropic key, DB password) live in
  environment-specific `.env` files: `apps/api/.env` and `apps/web/.env.local`.
  Both are gitignored (root `.gitignore`). Only `.env.example` /
  `.env.local.example` (placeholders, no real values) are committed.
- The Anthropic API key is read server-side only
  (`apps/api/src/tradingos_api/core/config.py`) and is never sent to or
  readable by the browser — `apps/web` never holds it.
- The local Postgres app role (`tradingos_app`) is a least-privilege role
  scoped to the `tradingos` database, not the `postgres` superuser (ADR-008).
  Its password was generated randomly (`secrets.token_urlsafe`), not chosen
  or guessed by the assistant.
- No `.env` files, logs, prompts, screenshots, or fixtures in this repo
  contain a real secret value as of Phase 1 — verified by inspection before
  the Phase 1 checkpoint commit.

## Least privilege

- Alpaca keys used in this project are **paper-trading keys only**. Nothing
  in `PaperBrokerProvider` (apps/api/src/tradingos_api/providers/broker.py)
  has a method that could place a live order — there is no live-order
  interface in this codebase at all (principle 10).
- Any future live-trading capability would need its own explicitly-flagged
  interface, gated on human confirmation immediately before each action
  (principle 11) — not a config flag flipped on the existing paper interface.

## Data sensitivity

- No real personal financial data exists in this system — it operates on a
  synthetic/paper portfolio and licensed market data (Alpaca), never scraped
  from paywalled or ToS-restricted sources (principle 12; see ADR-002 for why
  yfinance/Yahoo scraping was rejected).
- No PII beyond the single local user's own (non-shared) use of the app.

## Authn/authz

- **Implemented, Revision Prompt 16 (ADR-066).** Single-user password
  login (`hashlib.scrypt`, stdlib-only) issues a server-side, revocable
  session (opaque token, `token_hash` stored — never the raw token).
  Every business router requires a valid session
  (`core/dependencies.py::require_session()`); only `/health` and
  `/api/v1/auth/login`/`session` are reachable unauthenticated. Step-up
  re-authentication (`POST /auth/step-up`, 5-minute `STEP_UP_TTL`) exists
  for kill switch / cancel-all / mode changes / approval decisions —
  wiring those specific endpoints to *require* it is a separate,
  already-tracked follow-up task.
- **CSRF protection — implemented, Revision Prompt 16.** Double-submit
  cookie: login sets a second, non-httpOnly `tradingos_csrf` cookie; the
  frontend echoes its value as an `X-CSRF-Token` header on every
  mutating request (`apps/web/lib/api/client.ts`); the server rejects
  any POST/PUT/PATCH/DELETE where the header is missing or doesn't match
  the cookie (`core/auth.py::verify_csrf_token()`). GET/HEAD/OPTIONS are
  exempt.
- **Secure response headers — implemented, Revision Prompt 16.**
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: same-origin`, a restrictive `Permissions-Policy`,
  and a `Content-Security-Policy` (exempting only `/docs`/`/redoc`/
  `/openapi.json`, which need CDN-hosted Swagger UI assets) on every
  response (`core/security_headers.py`). `Strict-Transport-Security` is
  added once `environment != "local"` (sending it over plain local HTTP
  would be a lie the browser can't act on).
- **CORS — hardened, Revision Prompt 16.** Allow-list is env-driven
  (`Settings.cors_allowed_origins`, comma-separated), `allow_credentials
  =True` with the specific origin(s) echoed back (never `*`), and
  `allow_headers` is an explicit list (`Content-Type`, `X-CSRF-Token`)
  rather than `*`.
- If this app were ever exposed beyond the current user's own machine on
  a network route reachable by anyone but the operator, that would still
  require its own review (rate limiting beyond login, a real TLS
  termination point, `/docs` exposure) before that happens — tracked as
  a known limitation in README.md, not silently assumed already covered
  by the above.

## LLM-specific guardrails (detailed in docs/MODEL_GOVERNANCE.md)

- Server-side only; the model never receives raw DB credentials or executes
  SQL directly (tool-use pattern, not text-to-SQL).
- Tool allow-list with schema-validated parameters — **implemented,
  Phase 4** (`services/llm_tools.py`).
- Responses grounded in tool results only — the system prompt instructs the
  model to refuse to speculate beyond what tools returned (principle 4/7).
- Rate-limited endpoint — **implemented, Phase 4**
  (`POST /api/v1/ask`, `core/rate_limit.py`).

## Phase 7 review note (2026-08-03) — frontend introduces no new secret-handling surface

Reviewed `apps/web` end-to-end before the Phase 7 checkpoint:

- The Anthropic API key is never referenced anywhere under `apps/web` —
  confirmed by inspection of every `lib/api/*.ts` module. The only
  frontend-configurable value is `NEXT_PUBLIC_API_URL` (the API's own
  base URL, not a secret — deliberately `NEXT_PUBLIC_*` since it's not
  sensitive, unlike the Anthropic key which stays server-side-only in
  `apps/api`).
- No form in `apps/web` collects or transmits a credential, API key, or
  payment detail of any kind — every form (`OrderForm`,
  `StrategyVersionsPage`'s propose form, the ask chat input) only ever
  submits trading/strategy-configuration data to `apps/api`'s existing,
  already-reviewed endpoints.
- No new client-side storage was added (no `localStorage`/cookies/session
  storage) — all state is either server-derived (TanStack Query) or
  page-local React state that resets on reload.
- `apps/web`'s only outbound network calls are to `NEXT_PUBLIC_API_URL`
  (this app's own API) — no third-party script, analytics tag, or
  external API call exists anywhere in the frontend.

**Conclusion:** Phase 7 does not change this document's threat model —
still a single-user local tool, no new secret ever touches the browser.
(Historical note: at the time this was written, "no auth" was still
accurate — see the Authn/authz section above for Revision Prompt 16's
later change.)

## v2 Decision and Execution Amendment (2026-08-05) — order authority and Cowork boundary

PROJECT_INSTRUCTIONS.md's new "TradingOS v2 Decision and Execution
Amendment" section (`OA-*`/`SS-*`) adds security-relevant policy on top
of everything above:

- **Cowork is explicitly named as a non-exempt channel (SS-1/SS-5).**
  Broker credentials may never be sent to a Claude Cowork prompt, and a
  Cowork scheduled task is a **read-only** consumer of the morning
  decision plan — it cannot be an order-execution channel under any
  configuration. No Cowork integration exists in this codebase yet; this
  is a forward-looking constraint recorded before one is ever built, not
  a retrofit.
- **No text channel may reach the broker boundary (OA-7).** No LLM,
  scheduled job, news article, email, or notification may directly
  invoke order submission/replacement/cancellation — only the
  deterministic order service may. `tests/test_policy_order_authority.py::TestBrokerBoundaryIsSingleEntryPoint`
  proves this already holds structurally for the current codebase: the
  order-fill function (`_apply_fill`) and every order-mutating endpoint
  (`propose_order`/`confirm_order`/`cancel_order`/`import_fills`) are
  defined only in `routers/orders.py`, nowhere else under `src/`. This is
  a real, checked invariant today, not just a stated goal — Phase 8
  already retired the one component (`services/ask.py`'s LLM tool-use
  loop) that could have been a text-to-action risk.
- **Four-tier order authority (OA-1..OA-6).** `RESEARCH_ONLY`,
  `PAPER_MANUAL_APPROVAL`, `PAPER_AUTO_POLICY`, `LIVE_CONFIRM_EACH_ORDER`
  — implemented as a standalone, tested policy module
  (`apps/api/src/tradingos_api/policy/order_authority.py`,
  `assert_order_authorized()`), fail-closed on any ambiguous live-order
  identity. **Not yet wired into `routers/orders.py`** — today's API has
  no operating-mode concept at all; every existing order endpoint behaves
  like an ungated `PAPER_MANUAL_APPROVAL` (propose creates a `DRAFT`,
  confirm requires an explicit `POST .../confirm` call — a de facto
  confirmation step — but there is no `OrderAuthorityMode` value stored
  or checked anywhere). Wiring the real gate in is future work, tracked
  in docs/TASKS.md's "Phase 9+" section, not silently assumed to already
  be enforced.
- **Kill switch and cancel-all (OA-9/SS-4).** Required by the amendment;
  **not implemented**. No live broker integration exists in this
  codebase (principle 10, unchanged), so there is nothing to kill yet —
  but the control (and its own audit trail) must exist before any live
  or auto-policy order path is ever built, not added after the fact.
- **Approval binds the exact order (OA-8/SS-2/SS-3).** Required by the
  amendment for any future confirmation UI/API: account, symbol, side,
  quantity, order type, limit/stop prices, time in force, outside-hours
  flag, attached legs, maximum notional, recommendation version, and
  approval expiration, with any material change invalidating the
  approval. Not yet implemented — today's `POST /api/v1/orders/{id}/confirm`
  re-executes against the order row as currently stored, with no
  captured "this is what was approved" snapshot distinct from the order
  itself.

## Secret scanning + dependency scanning (Revision Prompt 16, ADR-070)

- **`.gitignore` gap fixed.** The old `.env` / `.env.local` /
  `.env.*.local` trio (root and `apps/web/.gitignore`) only matched
  `.local`-suffixed env files — a real, non-`.local` deployment file
  (`.env.production`, `.env.staging`, ...) would not have matched any of
  the three and could have been committed by an unwitting `git add -A`.
  Both files now use `.env*` with `!.env.example`/`!.env.*.example`
  negations to re-allow the committed placeholders. Verified: creating
  `apps/api/.env.production` and `apps/web/.env.production` now shows as
  ignored (`git check-ignore -v`), and the three tracked `.example`
  placeholders remain trackable.
- **Secret scanning — gitleaks, run against full history.** `gitleaks
  git --log-opts="--all" --config .gitleaks.toml` over all 32 commits:
  **no leaks found.** One false positive (a strategy-component name,
  `PRICE_ABOVE_EMA20`, in a generated test-evidence doc, tripped the
  generic-api-key entropy heuristic) is allowlisted by path in
  `.gitleaks.toml` with a documented reason — no rule was loosened, only
  that one known-safe match. Not yet wired into CI (task: CI pipeline);
  run it locally before any push until then.
- **Dependency scanning — backend (`pip-audit`, added to the `dev`
  dependency group in `pyproject.toml`, `uv.lock` regenerated).**
  `uv run pip-audit`: **no known vulnerabilities.**
- **Dependency scanning — frontend (`pnpm audit`).** Found 6
  vulnerabilities (2 moderate, 4 high), all transitive through build
  tooling (`next`'s bundled `sharp`/`postcss`, and a second `postcss`
  copy pulled in by `@tailwindcss/postcss`/`vite`/`vitest`) — none in
  code that runs in the browser or handles user input. Fixed by
  upgrading `next` 16.2.12 → 16.3.0 (resolves 5 of 6) and pinning the
  remaining transitive `nanoid` to `>=3.3.17` via a `pnpm-workspace.yaml`
  `overrides` entry (the `<3.3.17` copy came from the dev-only
  tailwindcss/vite/vitest toolchain, not from `next` itself). Re-run
  after both fixes: **no known vulnerabilities.** Verified the app still
  builds, type-checks, lints, and passes its full test suite after both
  changes (`next build`, `tsc --noEmit`, `eslint`, `vitest run` — all
  clean).

## Local dev environment note

Postgres auth on this dev machine uses `scram-sha-256` (encrypted password
auth), the PostgreSQL-installer default — not `trust`. Temporarily switching
to `trust` to reset a lost local password is standard PostgreSQL
documentation-sanctioned recovery practice, performed by the human operator
(not automated), and reverted immediately after (ADR-008 background).
