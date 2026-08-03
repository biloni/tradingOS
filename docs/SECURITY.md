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

## Local dev environment note

Postgres auth on this dev machine uses `scram-sha-256` (encrypted password
auth), the PostgreSQL-installer default — not `trust`. Temporarily switching
to `trust` to reset a lost local password is standard PostgreSQL
documentation-sanctioned recovery practice, performed by the human operator
(not automated), and reverted immediately after (ADR-008 background).
