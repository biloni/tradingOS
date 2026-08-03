# Tasks / Phase Roadmap

Each phase is worked in full (small, modular, tested, documented) before the
next begins. See PROJECT_INSTRUCTIONS.md "Working Method" for the process
every phase follows.

## Phase 1 — Foundations & Architecture (current)

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
- [ ] Phase 1 checkpoint commit

## Phase 2 — Data Ingestion & Indicators

- [ ] Concrete `AlpacaMarketDataProvider` implementing `MarketDataProvider`
- [ ] `Symbol`, `PriceBar` SQLAlchemy models + first Alembic migration
- [ ] Deterministic indicator calculations (versioned, unit-tested)
- [ ] Corporate-actions handling (splits/dividends) for equities/ETFs
- [ ] Synthetic fixtures for the default test suite (no live Alpaca calls
      required to pass tests)

## Phase 3 — Paper Portfolio & Trade Tracking

- [ ] Concrete `AlpacaPaperBrokerProvider`
- [ ] `PaperPortfolio`, `PaperPosition`, `PaperOrder` models + migration
- [ ] Order submission flow with human confirmation before any order fires
- [ ] Reconciliation against Alpaca's own paper-account position report

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
