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

- Single-user system, no authentication in the MVP (ADR-007). If this app
  were ever exposed beyond the current user's own machine, authentication
  would need to be added before that happens — tracked as a known limitation
  in README.md, not silently deferred.

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
still a single-user local tool, no auth, no new secret ever touches the
browser.

## Local dev environment note

Postgres auth on this dev machine uses `scram-sha-256` (encrypted password
auth), the PostgreSQL-installer default — not `trust`. Temporarily switching
to `trust` to reset a lost local password is standard PostgreSQL
documentation-sanctioned recovery practice, performed by the human operator
(not automated), and reverted immediately after (ADR-008 background).
