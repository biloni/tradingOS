# Architecture Decision Records

Format: each ADR is Context / Decision / Alternatives considered / Consequences.
ADRs are append-only — superseding a decision means adding a new ADR that
references the old one, not editing history.

## ADR-001: Monorepo layout — `apps/web` (Next.js) + `apps/api` (FastAPI)

**Context.** PROJECT_INSTRUCTIONS.md specifies Next.js/TypeScript for the web
tier and Python/FastAPI for the API tier, in a single repo unless a compelling
reason exists not to.

**Decision.** One repo, `apps/web` and `apps/api` as independent, separately
tooled projects (`pnpm` workspace for web, `uv` project for api), plus a
shared `docs/` and `infra/` at the root. No shared code package between them
in Phase 1 — nothing to share yet.

**Alternatives considered.** Two separate repos (rejected: adds deploy/version
coordination overhead for a single-person project with no team boundary to
justify it).

**Consequences.** Two toolchains to run locally (`uv run ...`, `pnpm ...`).
Documented clearly in README.md quickstart.

---

## ADR-002: Market data + paper-trading vendor — Alpaca Markets

**Context.** The app needs (a) OHLCV price history and quotes for US equities
and ETFs, and (b) a paper-trading brokerage account to place and track
simulated orders. This is a vendor and recurring-cost decision, confirmed with
the user directly (not defaulted silently), per the project's working method.

**Decision.** Alpaca Markets for both roles. Free tier covers paper trading
(unlimited, no cost) and market data via the IEX feed (real-time bars are a
paid add-on; free tier is suitable for a 2–10 day swing-trade horizon, not
intraday/day-trading).

**Alternatives considered.**
- *Polygon.io* — better data quality/latency, but no built-in paper brokerage;
  would require building the paper ledger fully in-house. Kept as a documented
  fallback in docs/PROVIDER_MATRIX.md if Alpaca's data license terms or rate
  limits become limiting.
- *IEX Cloud* — shut down in 2024; not viable.
- *yfinance / scraping Yahoo Finance* — rejected outright: violates principle
  12 (no scraping of prohibited sources; Yahoo's ToS restricts automated
  access).

**Consequences.** `MarketDataProvider` and `PaperBrokerProvider` interfaces
(apps/api/src/tradingos_api/providers/) are defined against Alpaca's data
shape conceptually, but remain Protocol-typed so a second provider could be
added later without touching callers. No Alpaca API calls exist yet — the
concrete client lands in Phase 2 (data) / Phase 3 (portfolio).

---

## ADR-003: Market universe — US equities + ETFs only for MVP

**Context.** Confirmed with the user directly. Options and crypto would add a
materially more complex data model (strikes/expirations/greeks, 24/7 market
hours) with no confirmed need for the MVP's swing-trading use case.

**Decision.** US-listed equities and ETFs only. `Symbol.assetType` is
constrained to `EQUITY | ETF` (see docs/DATA_DICTIONARY.md).

**Alternatives considered.** Equities + ETFs + options (rejected for MVP,
revisit once the core loop — ingestion → scoring → paper trade → review — is
proven on the simpler asset types).

**Consequences.** Corporate-actions handling (splits/dividends) only needs to
account for equity/ETF cases, not options-specific adjustments.

---

## ADR-004: Chart library — `lightweight-charts` over Recharts

**Context.** The brief's default technical direction names "a reliable
charting library" without pinning one. Swing-trade decision support needs
candlestick/OHLC charts with volume overlays, which Recharts (a general
category/line/bar charting library) does not render well.

**Decision.** `lightweight-charts` (TradingView's open-source canvas charting
library, MIT-licensed) for price/candlestick charts. Recharts (or an
equivalent) may still be used later for generic dashboards/analytics charts
(e.g., a P&L line chart) if a general-purpose need arises — this ADR only
scopes the *price chart* decision.

**Alternatives considered.** Recharts for everything (rejected: no native
candlestick support). D3 directly (rejected: far more implementation effort
for no benefit over a purpose-built financial charting library).

**Consequences.** One more frontend dependency, but a domain-appropriate one.

---

## ADR-005: Python tooling — `uv` + `ruff` + `mypy`; TS tooling — `pnpm` + ESLint + `tsc`

**Context.** PROJECT_INSTRUCTIONS.md specifies `pnpm` for TypeScript and `uv`
for Python "unless current stable tooling suggests a better documented
choice." No better-documented alternative was found.

**Decision.** `uv` for Python dependency/venv/version management, `ruff` for
both linting and formatting (replacing the separate black+isort+flake8
stack), `mypy --strict` for type checking. `pnpm` for TS, ESLint
(`eslint-config-next`) + `tsc --noEmit` for type checking.

**Consequences.** Single fast tool (`ruff`) covers what used to be 2–3 tools
on the Python side.

---

## ADR-006: Redis and Playwright deferred, not adopted, for Phase 1

**Context.** PROJECT_INSTRUCTIONS.md explicitly says "Redis only when a
demonstrated use case requires it," and the default technical direction lists
Playwright end-to-end tests as part of the testing stack.

**Decision.** Neither is installed in Phase 1. Phase 1 has no caching/queueing
need (no background jobs exist yet) and no real user journey beyond a health
check page (a Playwright e2e test of "does the health page load" would just
duplicate what the Vitest smoke test already covers).

**Consequences.** Revisit Redis when a background job (e.g., scheduled market
data ingestion) is designed in Phase 2. Revisit Playwright once a real
multi-step user journey exists (e.g., Phase 3's paper-order flow or Phase 4's
BP-style... — n/a for TradingOS, see Phase 4 scoring review flow).

---

## ADR-007: No auth/multi-tenancy in MVP

**Context.** This is a personal, single-user system per the mission statement
— there is no second user to isolate.

**Decision.** No authentication, no user table, no row-level security in the
MVP. `docs/SECURITY.md` documents this explicitly as a scoped-out concern
rather than an oversight.

**Consequences.** If the app were ever shared with another person, this would
need to be revisited before doing so — noted in README "known limitations."

---

## ADR-008: Local Postgres via native Windows install (winget) rather than Docker Desktop

**Context.** The default technical direction calls for Docker Compose "plus
non-container commands where practical." This dev machine had neither Docker
nor Postgres installed. Installing Docker Desktop on Windows typically
requires enabling WSL2/Hyper-V, which is a system-settings change outside
what an assistant should perform autonomously.

**Decision.** Installed PostgreSQL 16 natively via `winget install
PostgreSQL.PostgreSQL.16` — a standard application installer, no
virtualization features touched. `infra/docker-compose.yml` still exists and
is documented for other machines / a future CI environment, but the native
install is the primary path for this developer's local setup.

**Consequences.** README documents both paths. A dedicated least-privilege
role (`tradingos_app`) and database (`tradingos`) were created rather than
using the `postgres` superuser at runtime.

---

## ADR-009: Alpaca SDK (`alpaca-py`), not hand-rolled HTTP

**Context.** Phase 2 needed a concrete `MarketDataProvider` implementation
against Alpaca's market data API.

**Decision.** Use the official `alpaca-py` package (`StockHistoricalDataClient`)
rather than calling Alpaca's REST endpoints directly with `httpx`/`requests`.

**Alternatives considered.** Hand-rolled HTTP client (rejected: would
duplicate auth header handling, pagination, and response-shape parsing that
the official SDK already gets right and keeps up to date).

**Consequences.** Adds `alpaca-py` and its transitive deps (`pandas`,
`numpy`, `websockets`, etc. — see docs/DEPENDENCIES.md) to `apps/api`.
`AlpacaMarketDataProvider` (providers/alpaca_market_data.py) wraps the SDK
behind the existing `MarketDataProvider` Protocol so callers never see the
SDK's own types directly.

---

## ADR-010: Corporate actions via Alpaca's split-adjusted bars, not a custom
adjustment engine

**Context.** Phase 2's task list calls for "corporate-actions handling
(splits/dividends)." Building adjustment math from raw corporate-action data
would duplicate a well-solved problem.

**Decision.** Request bars with `adjustment="split"` (split-adjusted, not
dividend-adjusted) from Alpaca. Split-only matches how charting platforms
display default price series and is what SMA/RSI/MACD-style technical
indicators expect; dividend adjustment depresses historical closes in a way
suited to total-return analysis, not swing-trade price-action signals.

**Alternatives considered.** `adjustment="all"` (both split + dividend) —
rejected for the reason above. `adjustment="raw"` + custom adjustment engine
— rejected as unnecessary re-implementation of a vendor-solved problem.

**Consequences.** `PriceBar.adjustment` is stored as `"split"` on every row
so this choice is visible in the data itself, not just in code. A future
phase wanting total-return analysis would add a second, explicitly-dividend-
adjusted series rather than changing this one.

---

## ADR-011: `PriceBar` is append-only; `get_latest_price_bars()` is the one
shared derivation helper

**Context.** docs/DATA_DICTIONARY.md already stated `PriceBar` facts are
never mutated in place. Phase 2 had to decide the concrete mechanics of that.

**Decision.** No unique constraint on `(symbol_id, as_of, timeframe)` —
multiple rows for the same date are allowed (e.g. a later corrective
re-fetch). `services/price_bars.py`'s `get_latest_price_bars()` is the single
place every caller (indicators now, scoring/backtesting later) reads
"current" prices through, always picking the max-`fetched_at` row per date.

**Alternatives considered.** Upsert on `(symbol_id, as_of, timeframe)`
(rejected: silently overwriting a prior fetch loses the audit trail of what
was observed when — contradicts principle 3/9).

**Consequences.** Re-running the ingestion script repeatedly grows the table
rather than upserting — documented plainly in the script's docstring and
docs/STATUS.md so it reads as intentional, not a bug.

---

## ADR-012: `Indicator` rows are idempotent (insert-if-not-exists), not
append-only

**Context.** Unlike `PriceBar` (an observed fact), `Indicator` is a
deterministic calculation (principle 6) — given the same inputs and the same
formula version, the output is always the same value.

**Decision.** Unique constraint on `(symbol_id, as_of, indicator_name,
version)`; `compute_indicators_for_symbol()` uses `INSERT ... ON CONFLICT DO
NOTHING ... RETURNING id` and counts only the rows Postgres actually
inserted. (Note: `cursor.rowcount` was tried first and observed to return
`-1` for this bulk multi-row upsert under psycopg3 — unreliable, so
`RETURNING` is used instead for a portable, correct count.)

**Alternatives considered.** Append-only like `PriceBar` (rejected: there's
no meaningful "correction" concept for a pure function of existing data — a
different answer only happens when the formula version changes, which is
already handled by bumping `FORMULA_VERSION`).

**Consequences.** Re-running the ingestion script against unchanged price
history is a safe no-op for indicators (verified: second run reported 0 new
rows) — the same run does still insert new `PriceBar` rows per ADR-011.

---

## ADR-013: `PaperPosition` is a derived view, not a table; cost basis is a
simple weighted average, not FIFO/LIFO tax lots

**Context.** Phase 3 needed to decide how "current holdings" are represented
— a persisted table updated alongside orders, or computed on read.

**Decision.** No `PaperPosition` table. `services/portfolio.py`'s
`get_derived_positions()` computes net quantity and a weighted-average entry
price from filled `PaperOrder` rows, on every read. Same reasoning as
`PriceBar`/`get_latest_price_bars()` (ADR-011): a derived value can't drift
out of sync with the events that produce it, because it's never stored
independently of them.

**Alternatives considered.** A `PaperPosition` table updated transactionally
alongside each fill (rejected: two sources of truth that can diverge is
exactly the bug class `get_latest_price_bars()` was designed to avoid).
FIFO/LIFO tax-lot cost-basis accounting (rejected for MVP scope: a simple
weighted average across BUY fills is enough to show P&L direction; lot-level
accounting matters for tax reporting, which is out of scope for a paper-
trading decision-support tool).

**Consequences.** `docs/DATA_DICTIONARY.md`'s `PaperPosition` entry is
annotated as derived, not dropped — it's still a real concept in the system,
just not its own storage. No short selling is allowed in this MVP (a SELL
can't exceed the derived held quantity) — simpler than modeling margin/short
positions, and matches typical retail cash-account behavior.

---

## ADR-014: Two-step propose-then-confirm order flow

**Context.** Principle 11 requires human confirmation immediately before any
order-placing action — not just for live trading (which doesn't exist in
this app) but as this app's whole design philosophy: decision-support, not
autonomous action.

**Decision.** `POST /api/v1/paper-orders` only validates and records a
`DRAFT` row — nothing reaches Alpaca. `POST /api/v1/paper-orders/{id}/confirm`
is the sole action that calls `AlpacaPaperBrokerProvider.submit_paper_order()`,
and only operates on a `DRAFT` order (not retriable once it has moved past
that state).

**Alternatives considered.** A single `POST` that both validates and submits
(rejected: collapses proposal and action into one step, which is exactly
what principle 11 says not to do).

**Consequences.** A future UI's "Buy"/"Sell" button maps to `propose`; its
"Confirm" button maps to `confirm`. Capital/position sufficiency is
re-validated at both steps (prices/positions can move between propose and
confirm).

---

## ADR-015: `AuditEvent` — generic, untyped `ref_id`, introduced this phase

**Context.** Principle 9 requires an audit trail for every user action,
order, and override. Phase 3 is the first phase with real user actions to
audit (propose/confirm/refresh/cancel a paper order).

**Decision.** One `audit_events` table: `record_type` (string) + `ref_id`
(plain integer, no FK) + `snapshot` (JSON) + `created_at`, written only
through `services/audit.py`'s `record_audit_event()`. `ref_id` is untyped
because a single audit log spans many different entity types over the
life of the app — a column can't FK to more than one target table.

**Alternatives considered.** A separate audit table per entity type
(rejected: multiplies migrations/models for a cross-cutting concern that's
conceptually one thing — "what happened and when").

**Consequences.** Querying "all audit events for order 42" is
`WHERE record_type = 'PAPER_ORDER_...' AND ref_id = 42` rather than a typed
join — an accepted tradeoff for a generic audit log.

---

## ADR-016: Explicit order-status refresh, not a webhook/polling daemon

**Context.** Live-verified against the real Alpaca paper API (see
docs/TEST_EVIDENCE.md): a submitted market order's immediate response
reported status `new` (not yet filled); the actual fill landed about 0.8s
later. `submit_paper_order()`'s response alone is therefore not reliable
for capturing the final fill — this is normal broker behavior, not an edge
case, and the original Phase 3 plan hadn't accounted for it.

**Decision.** `PaperBrokerProvider` gained a fourth method,
`get_paper_order_status()`. `confirm` does one immediate re-check right
after submission (catches the common same-cycle fill case observed in
testing). A new `POST /api/v1/paper-orders/{id}/refresh` endpoint re-syncs
status/fill fields for any order still `SUBMITTED`/`PARTIALLY_FILLED` later.

**Alternatives considered.** A background poller or Alpaca's websocket
trade-updates stream (rejected for this phase: real scheduler/background-job
infrastructure, deferred per the same reasoning as ADR-006 — no demonstrated
need for automatic polling yet when an explicit refresh action covers the
MVP's manual/API-driven usage). Blocking `confirm` with a longer retry loop
(rejected: an HTTP request shouldn't block for an unbounded, market-dependent
amount of time — a limit order might not fill for hours).

**Consequences.** A future UI polling `/refresh` for open orders (or a
proper websocket subscription) is the natural next step once there's a
UI to drive it — not built now, since there's no UI yet (Phase 7).

---

## ADR-017: LLM model — `claude-sonnet-5`, verified via the `claude-api` skill
at implementation time

**Context.** Phase 4 needed a concrete `AnthropicLLMProvider`. Model IDs and
pricing drift over time and must never be guessed from training data
(PROJECT_INSTRUCTIONS.md's engineering rules / the `claude-api` skill's own
warning about stale priors).

**Decision.** `claude-sonnet-5`, confirmed current via the `claude-api` skill
on 2026-08-03 (intro pricing $2.00/$10.00 per million input/output tokens
through 2026-08-31). `thinking` is left unset (adaptive by default) rather
than explicitly disabled, and no sampling params (`temperature`/`top_p`/
`top_k`) are set — this model rejects non-default values for those.

**Alternatives considered.** `claude-opus-5` (rejected: this is a
synthesis/explanation task over already-computed deterministic data, not a
task requiring frontier reasoning depth — Sonnet-tier is the right cost/
capability point for a personal app's NL query feature). Pinning to a
dated snapshot ID (rejected: the skill's guidance is to use the bare
model-family ID, never a training-data-recalled dated suffix).

**Consequences.** `providers/anthropic_llm.py`'s `MODEL` constant is the one
place this pins to a specific model; re-verify via the skill before ever
bumping it.

---

## ADR-018: `compute_recommendation` is the one tool allowed to have a side
effect (persisting a `Recommendation`)

**Context.** Every other Phase 4 tool (`query_symbols`, `get_price_summary`,
`get_indicators`, `get_recommendations`) is a pure read. Principle 7 says
the model never executes anything directly — but generating a
recommendation is the actual point of the feature, not an incidental side
effect the model triggers as a side-quest.

**Decision.** `compute_recommendation` both computes the deterministic score
(`services/scoring.py`, no LLM involvement in the number itself — principle
6) and persists exactly one `Recommendation` row, superseding any prior
`ACTIVE` row for the same symbol rather than deleting it. This is
fundamentally different from a real side effect like placing an order: it's
fully deterministic given its inputs, versioned (`strategy_version_id`,
`prompt_version`), and auditable — there is no external system it commits
to, unlike Alpaca order placement (which stays behind Phase 3's separate
propose/confirm gate, entirely untouched by this endpoint).

**Alternatives considered.** Splitting into a pure `compute_score` tool plus
a separate, explicit "save this recommendation" step (rejected for MVP: adds
a confirmation step for an action that carries none of the real-world risk
principle 11 is protecting against — no money moves, no order is placed;
revisit only if recommendation history needs its own review gate later).

**Consequences.** `services/llm_tools.py`'s docstring calls this out
explicitly so a future reader doesn't assume every tool is side-effect-free
by default.

---

## ADR-019: Stateless per-request `/api/v1/ask`, tool-use loop capped at 5
iterations

**Context.** Phase 4's NL query endpoint needs to let the model call
several tools before answering (e.g., look up a symbol, pull indicators,
then compute a recommendation) without risking an unbounded request or
unbounded Anthropic spend per call.

**Decision.** `services/ask.py`'s `answer_question()` runs the full
call → execute tools → feed results back → call again cycle within one
HTTP request/response, capped at `MAX_ITERATIONS = 5`. No `Conversation`
table exists — a caller wanting multi-turn context resends prior turns
itself. Every single Anthropic call (not just the final one) is logged to
`LLMCallLog`, so a multi-tool-call request produces multiple log rows.

**Alternatives considered.** Persisted server-side conversation history
(rejected for MVP: no confirmed multi-turn UI need yet — Phase 7 owns the
chat UI and can resend history itself if needed). An unbounded loop
(rejected: an adversarial or confused tool-call sequence could otherwise
run indefinitely and burn Anthropic spend with no ceiling).

**Consequences.** A question needing more than 5 tool-call rounds gets a
plain "try a more specific question" fallback message rather than hanging
or erroring — tested explicitly (`tests/test_ask.py::TestIterationCap`).

---

## ADR-020: `LLMProvider.complete()` widened for genuine tool-use (messages,
tools, stop_reason, raw_content)

**Context.** The Phase 1 `LLMProvider` interface (never yet implemented)
assumed flat string messages. Anthropic's real tool-use protocol needs
nested content blocks (text/tool_use/tool_result) round-tripped verbatim
across turns — a caller that reconstructed messages from `text`/`tool_calls`
alone would drop thinking blocks or malform the conversation.

**Decision.** `messages` widened from `list[dict[str, str]]` to
`list[dict[str, Any]]`; `complete()` gained an optional `tools` parameter;
`LLMResponse` gained `stop_reason: str` and `raw_content: list[dict[str,
Any]]` — the exact content blocks the model returned, serialized as plain
dicts. Callers must echo `raw_content` back on the next turn, not a
reconstruction.

**Alternatives considered.** Keeping the narrow Phase 1 shape and having
`AnthropicLLMProvider` translate internally (rejected: would require the
provider to fabricate a lossy round-trip representation, defeating the
purpose of a provider-neutral interface that's supposed to expose what
actually happened).

**Consequences.** This is a breaking change to an interface with no prior
callers (nothing implemented it before Phase 4), so no migration cost
anywhere else in the codebase.

---

## ADR-021: In-process token-bucket rate limiter for `/api/v1/ask`, no Redis

**Context.** `docs/MODEL_GOVERNANCE.md` commits to rate-limiting the NL
query endpoint to bound Anthropic spend against a runaway client. This is a
single-user, single-process personal app (same premise as ADR-006's Redis
deferral).

**Decision.** `core/rate_limit.py`'s `TokenBucketRateLimiter` — an
in-memory, thread-safe token bucket (5-request burst, 1 token per 12
seconds refill = 5/min steady state), instantiated once at module scope and
shared across requests within the running process. Exceeding it returns
`429`.

**Alternatives considered.** Redis-backed rate limiting (rejected: no
multi-process/multi-instance deployment exists to require shared state
across processes — same reasoning as ADR-006). A per-IP or per-API-key
limiter (rejected: no auth/multi-tenancy exists, ADR-007 — there is exactly
one caller).

**Consequences.** The limiter resets on process restart, which is
acceptable for a personal tool bounding accidental spend, not defending
against determined multi-tenant abuse.
