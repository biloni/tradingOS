# Status

**Current phase:** Phase 2 — Data Ingestion & Indicators
**Last updated:** 2026-08-03

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint commit `0a2644d`.
- **Phase 2:**
  - `Symbol`, `PriceBar`, `Indicator` models + migration `bd027d9f35a2`,
    applied to local Postgres (downgrade/upgrade round-trip verified clean).
  - `AlpacaMarketDataProvider` (concrete `MarketDataProvider`), backed by
    the official `alpaca-py` SDK, split-adjusted bars (ADR-009/010).
  - `services/price_bars.py` (shared latest-bar derivation helper) and
    `services/indicators.py` (SMA/EMA/RSI/MACD/Bollinger/ATR, all
    unit-tested against hand-verifiable invariants, not textbook numbers).
  - Ingestion entrypoint (`scripts/ingest_prices.py`) and 3 read endpoints
    (`/api/v1/symbols`, `.../{ticker}/bars`, `.../{ticker}/indicators`).
  - User provided real Alpaca paper-trading API keys (dropped into the
    gitignored `apps/api/.env`, never committed). **Live ingestion run
    against real Alpaca data**: 30 symbols upserted, 14,970 price bars,
    171,270 indicator rows. All 3 endpoints hit directly and confirmed
    returning real AAPL price/indicator data end-to-end.
  - 23/23 tests passing, `ruff`/`mypy --strict` clean on all new code.
  - All docs updated: ADR-009 through ADR-012, docs/DATA_DICTIONARY.md,
    docs/API_CONTRACTS.md, docs/TASKS.md, docs/DEPENDENCIES.md.

## In progress / next

- Fill docs/TEST_EVIDENCE.md with Phase 2's exact commands/output.
- Create the Phase 2 checkpoint commit.
- **Then stop and wait** — Phase 3 (paper portfolio & trade tracking) does
  not start until explicitly requested.

## Known blockers

None.

## Notable bug caught and fixed this phase

`compute_indicators_for_symbol()` initially reported row-insert counts via
`CursorResult.rowcount`, which returned `-1` for the bulk `INSERT ... ON
CONFLICT DO NOTHING` under psycopg3 (a real, observed driver quirk, not a
theoretical one — surfaced during the live ingestion run). Fixed by using
`RETURNING id` and counting the returned rows instead, which is portable and
correct regardless of driver rowcount reporting (ADR-012). Verified: the
live run's underlying data was correct throughout (14,400 SMA_20 rows = 480
eligible days × 30 symbols, exactly as expected) — only the console-reported
count was wrong, not the persisted data.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008).
- Playwright e2e tests, Redis (ADR-006).
- Scheduler/background-job wiring for ingestion — manual on-demand script
  only until a recurring need is demonstrated (same reasoning as ADR-006).
