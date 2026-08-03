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

## Phase 5 — Backtesting (current)

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
- [ ] Phase 5 checkpoint commit

## Phase 6 — Learning / Strategy-Review Loop

- [ ] Strategy-change proposal flow: backtest report + comparison against the
      current `StrategyVersion` + explicit user approval before activation
      (principle 16) — no auto-activation path exists

## Phase 7 — UI Polish & Documentation Hardening

- [ ] Full dashboard, charts, review flows
- [ ] docs/USER_GUIDE.md expanded to cover every shipped feature
- [ ] Final security/test-strategy review pass
