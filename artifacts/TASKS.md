# Tasks / Phase Roadmap

Each phase is worked in full (small, modular, tested, documented) before the
next begins. See PROJECT_INSTRUCTIONS.md "Working Method" for the process
every phase follows.

## Phase 1 — Foundations & Architecture

- [x] Repo scaffold: `apps/web` (Next.js), `apps/api` (FastAPI), `infra/`
- [x] Vendor ADRs confirmed with user: Alpaca (data+broker), US equities+ETFs
      scope, `lightweight-charts`, tooling choices, Redis/Playwright deferral
- [x] `apps/api`: FastAPI app, `/health` endpoint, Settings, DB session
      scaffolding, provider `Protocol` interfaces (no concrete
      implementations), Alembic initialized (no domain migrations)
- [x] `apps/web`: Next.js App Router, Tailwind, TanStack Query, health/status
      page calling the API, `lightweight-charts` installed for later use
- [x] Local Postgres running natively (ADR-008), dedicated `tradingos_app`
      role + `tradingos` database created
- [x] Lint/format/type-check/tests passing on both apps
- [x] All 15 required docs + DEPENDENCIES.md written
- [x] Verification workflow run end-to-end, docs/TEST_EVIDENCE.md filled in
- [x] Phase 1 checkpoint commit (`0a2644d`)

## Phase 2 — Data Ingestion & Indicators

- [x] Concrete `AlpacaMarketDataProvider` implementing `MarketDataProvider`
- [x] `Symbol`, `PriceBar`, `Indicator` SQLAlchemy models + first Alembic
      migration (`bd027d9f35a2`)
- [x] Deterministic indicator calculations (SMA/EMA/RSI/MACD/Bollinger/ATR,
      versioned via `FORMULA_VERSION`, unit-tested against hand-verifiable
      invariants)
- [x] Corporate-actions handling: delegated to Alpaca's split-adjusted bars
      (ADR-010), not a custom adjustment engine
- [x] Synthetic fixtures for the default test suite (mocked `alpaca-py`
      client, in-memory SQLite for endpoint tests — no live Alpaca calls or
      credentials required to pass `pytest`)
- [x] Ingestion entrypoint (`scripts/ingest_prices.py`) + 3 read endpoints
      (`/api/v1/symbols`, `.../bars`, `.../indicators`)
- [x] Live verification: real Alpaca keys provided, ingestion run against
      real data (30 symbols, 14,970 price bars, 171,270 indicator rows),
      endpoints hit and confirmed returning real data
- [x] Phase 2 checkpoint commit (`c2caa4c`)

## Phase 3 — Paper Portfolio & Trade Tracking

- [x] Concrete `AlpacaPaperBrokerProvider` (submit, status refresh, cancel,
      get positions — the status-refresh method was added mid-phase after
      live testing showed fills are asynchronous, ADR-016)
- [x] `PaperPortfolio`, `PaperOrder` models + migration (`6fa6b9fd2ff4`).
      `PaperPosition` is a derived view, not a table (ADR-013)
- [x] Two-step propose → confirm order flow with human confirmation before
      anything reaches Alpaca (ADR-014); capital/position sufficiency
      validated at both steps (principle 1)
- [x] `AuditEvent` audit trail introduced (ADR-015), written on every
      propose/confirm/refresh/cancel
- [x] Reconciliation endpoint (`GET /api/v1/portfolio/reconciliation`)
      against Alpaca's own paper-account position report
- [x] 17 new tests (provider mapping, order-flow validation, propose→confirm
      happy path, double-confirm rejection, async-fill catch-up, cancel,
      reconciliation match/mismatch) — 40/40 passing, no live API required
- [x] Live verification: proposed + confirmed a real 1-share SPY paper
      order, caught its asynchronous fill via `/refresh`, confirmed
      portfolio cash/position and reconciliation reflect the real Alpaca
      paper account exactly (see docs/TEST_EVIDENCE.md)
- [x] Phase 3 checkpoint commit (`811c5bd`)

## Phase 4 — Scoring Engine & LLM Synthesis

- [x] Concrete `AnthropicLLMProvider` (`claude-sonnet-5`, verified via the
      `claude-api` skill — ADR-017)
- [x] Deterministic scoring formulas (configurable via `StrategyVersion.config`,
      versioned per principle 8 — `services/scoring.py`)
- [x] `StrategyVersion`, `Recommendation`, `LLMCallLog` models + migration
      (`cd811cf4102b`), plus `PaperOrder.linked_recommendation_id`
- [x] Tool-use NL query endpoint (`POST /api/v1/ask`) with a
      schema-validated tool allow-list (`services/llm_tools.py`, 5 typed
      tools) — `compute_recommendation` is the one deliberate exception to
      side-effect-free (ADR-018)
- [x] Prompt versioning + cost tracking wired to `LLMCallLog`
      (`services/ask.py`, `services/llm_cost.py`)
- [x] Confidence calibration approach documented (docs/MODEL_GOVERNANCE.md)
      before any confidence number is surfaced as if it were a probability
      (principle 15) — bands are deterministic signal-agreement counts, not
      the LLM's self-report
- [x] In-process rate limiting (`core/rate_limit.py`, ADR-021) and a 5-call
      tool-use iteration cap (ADR-019)
- [x] 31 new tests this phase (scoring invariants, provider mapping,
      dispatcher validation, orchestration loop, endpoint rate-limit/
      validation) — 71/71 passing, no live API required
- [x] Live verification: real `/api/v1/ask` call against the real Anthropic
      API, `LLMCallLog` row inspected (see docs/TEST_EVIDENCE.md)
- [x] Phase 4 checkpoint commit (`fa66912`)

## Phase 5 — Backtesting

- [x] `BacktestRun` model + migration (`130bfdd45919`)
- [x] Historical replay engine: next-bar-open fills, no look-ahead bias
      (ADR-022), universe never filtered by today's `active` flag, no
      survivorship bias for this fixed watchlist (ADR-025) —
      `services/backtest.py`
- [x] Configurable entry/exit/position-sizing rule, versioned per run
      (ADR-023); backtests persist only in `BacktestRun.results_summary`,
      never `PaperOrder` rows (ADR-024)
- [x] `POST /api/v1/backtests` (+ list/detail), runs synchronously — no
      background job needed yet
- [x] Backtest report format (equity curve, trade log, summary metrics)
      that Phase 6's approval gate will compare a candidate
      `StrategyVersion` against
- [x] 21 new tests this phase (pure-core fill-timing/exit/sizing/metrics
      invariants incl. the no-look-ahead headline test, DB/endpoint tests
      incl. the survivorship-bias fixture) — 92/92 passing, no live API
      required (no Alpaca/Anthropic call needed this phase at all)
- [x] Live verification: real backtest run against the ~2-year real
      ingested history, `BacktestRun` row inspected (see
      docs/TEST_EVIDENCE.md)
- [x] Phase 5 checkpoint commit (`29a0763`)

## Phase 6 — Learning / Strategy-Review Loop

- [x] `StrategyVersion` gains a real 4-state lifecycle (`PROPOSED`/
      `ACTIVE`/`REJECTED`/`SUPERSEDED`), replacing `is_active: bool`
      outright (migration `eed7cb451bdc`, ADR-027)
- [x] Proposals are user/operator-submitted candidate configs, not an
      autonomous optimizer (ADR-026) — `POST /api/v1/strategy-versions`,
      schema-validated against the exact shape `compute_score()` expects
- [x] `POST /{id}/compare`: fresh backtest for candidate + active with
      identical params, persists 2 real `BacktestRun` rows, never changes
      candidate status
- [x] `POST /{id}/approve`: requires `PROPOSED`; re-runs the comparison
      itself for the audit snapshot (ADR-028, never trusts a prior
      `/compare`); activates the candidate, supersedes the previous
      active version; never enforces a numeric approval bar — a human
      decides
- [x] `POST /{id}/reject`: requires `PROPOSED`; no backtest re-run
- [x] Every proposal/approval/rejection writes its own `AuditEvent`
      (`STRATEGY_VERSION_PROPOSED`/`APPROVED`/`REJECTED` — principle 9)
- [x] 15 new tests this phase (pure `compute_comparison_delta` deltas,
      propose/compare/approve/reject state-machine + audit-trail
      endpoint tests) — 107/107 passing, no live API required (no new
      vendor this phase either)
- [x] Live verification: real propose → compare → approve flow against
      the real ingested data, `strategy_versions`/`audit_events` rows
      inspected (see docs/TEST_EVIDENCE.md)
- [x] Phase 6 checkpoint commit (`3fdbfac`)

## Phase 7 — UI Polish & Documentation Hardening

- [x] Full dashboard, charts, review flows
      - Dashboard: portfolio snapshot + health status + quick links
      - Symbols list + detail (candlestick chart + latest-indicators
        readout — no ranged overlay, the single-day `/indicators`
        contract doesn't support one)
      - Portfolio: holdings, propose→confirm→(refresh) paper-order flow,
        reconciliation panel
      - Ask: NL query chat with grounded recommendation chips and
        429/503/422-specific error copy
      - Backtests: run-new form, list, `BacktestReport` (metrics + equity
        curve + trade log)
      - Strategy versions: structured propose form, list,
        propose→compare→approve/reject state machine (`CompareView`)
      - Shared `components/ui/` kit + persistent sidebar (ADR-029)
- [x] docs/USER_GUIDE.md expanded to cover every shipped feature (full
      rewrite, one section per page/flow, plus known limitations)
- [x] Final security/test-strategy review pass — docs/SECURITY.md dated
      note (frontend introduces no new secret-handling surface),
      docs/TEST_STRATEGY.md's Playwright layer marked implemented
- [x] 20 new Vitest/RTL component tests: paper-order propose→confirm +
      error states, strategy propose→compare→approve/reject state
      machine + error states, ask page recommendation rendering +
      429/503/422 states, `BacktestReport` data-shape/empty-state
      coverage (jsdom can't render `<canvas>`, so chart components are
      mocked in these tests rather than rendered)
- [x] One Playwright e2e test (`e2e/paper-order-flow.spec.ts`, ADR-030)
      against real dev + API servers — passing
- [x] Bug found and fixed while writing tests: `CompareView.tsx`'s
      `DeltaMetric` parsed an already `%`-suffixed string with `Number()`,
      producing `NaN` and silently breaking the +/− sign and tone on
      every delta metric (ADR-031)
- [x] Live click-through of the full demo path (dashboard → symbol chart
      → propose/confirm a paper order → run a backtest → propose/
      compare/reject a strategy version → ask a question) — see
      docs/TEST_EVIDENCE.md
- [x] Phase 7 checkpoint commit
