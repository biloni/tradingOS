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

## Phase 3 — Paper Portfolio & Trade Tracking (current)

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
- [ ] Phase 3 checkpoint commit

## Phase 4 — Scoring Engine & LLM Synthesis

- [ ] Concrete `AnthropicLLMProvider`
- [ ] Deterministic scoring formulas (configurable, versioned per principle 8)
- [ ] `Recommendation`, `StrategyVersion`, `LLMCallLog` models + migration
- [ ] Tool-use NL query endpoint with a schema-validated tool allow-list
- [ ] Prompt versioning + cost tracking wired to `LLMCallLog`
- [ ] Confidence calibration approach documented before any confidence number
      is surfaced as if it were a probability (principle 15)

## Phase 5 — Backtesting

- [ ] `BacktestRun` model + migration
- [ ] Historical replay engine: no look-ahead bias, no survivorship bias,
      realistic fills (principle 14)
- [ ] Backtest report format used by Phase 6's approval gate

## Phase 6 — Learning / Strategy-Review Loop

- [ ] Strategy-change proposal flow: backtest report + comparison against the
      current `StrategyVersion` + explicit user approval before activation
      (principle 16) — no auto-activation path exists

## Phase 7 — UI Polish & Documentation Hardening

- [ ] Full dashboard, charts, review flows
- [ ] docs/USER_GUIDE.md expanded to cover every shipped feature
- [ ] Final security/test-strategy review pass
