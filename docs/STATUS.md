# Status

**Current phase:** Phase 5 — Backtesting
**Last updated:** 2026-08-03

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint `0a2644d`.
- **Phase 2** (Data Ingestion & Indicators) — checkpoint `c2caa4c`.
- **Phase 3** (Paper Portfolio & Trade Tracking) — checkpoint `811c5bd`.
- **Phase 4** (Scoring Engine & LLM Synthesis) — checkpoint `fa66912`.
- **Phase 5:**
  - `BacktestRun` model + migration `130bfdd45919` (downgrade/upgrade
    round-trip verified clean, no enum types needed).
  - `services/backtest.py`: a pure simulation core
    (`run_backtest_simulation()`, no DB/ORM) plus a thin DB-facing wrapper
    (`run_backtest()`) — mirrors the established pure-function/DB-
    orchestrator split from `indicators.py`/`scoring.py`/`llm_tools.py`.
  - Fill-timing convention: every entry/exit fills at the *next* bar in a
    symbol's own series, never same-day-close (ADR-022) — the concrete
    "no look-ahead bias" answer for this codebase.
  - Configurable, versioned entry/exit/position-sizing rule matching the
    2–10 day swing horizon (ADR-023); backtests persist only in
    `BacktestRun.results_summary`, never `PaperOrder` rows (ADR-024).
  - Survivorship-bias mitigation scoped to this system's fixed 30-name
    watchlist: the universe is every known `Symbol` regardless of today's
    `active` flag (ADR-025).
  - `POST /api/v1/backtests` (+ `GET` list/detail), runs synchronously —
    no background job needed for the current universe/window size.
  - 92/92 tests passing (21 new this phase: pure-core fill-timing, exit
    conditions, no-pyramiding, position sizing, hand-verified win-rate/
    drawdown metrics, and the headline no-look-ahead test; DB/endpoint
    tests including the survivorship-bias fixture), `ruff`/`mypy --strict`
    clean, no live API required to pass (no Alpaca/Anthropic call needed
    this phase at all).
  - **Live-verified**: a real `POST /api/v1/backtests` call over the full
    30-symbol, ~2-year (499 trading day) real ingested history completed
    in 4.5 seconds — 847 trades, 15.03% total return vs. SPY's 44.39%
    buy-and-hold over the same window, all internal numbers (exit-reason
    counts, one hand-recomputed trade's P&L, the final equity-curve point
    vs. `ending_equity`) verified consistent. See docs/TEST_EVIDENCE.md
    for full numbers.

## In progress / next

- Create the Phase 5 checkpoint commit.
- **Then stop and wait** — Phase 6 (learning / strategy-review loop) does
  not start until explicitly requested.

## Known blockers

None.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008), Playwright e2e, Redis (ADR-006/021).
- Automatic order-status polling / websocket trade-updates subscription
  (ADR-016). FIFO/LIFO tax-lot cost-basis accounting (ADR-013).
- Persisted multi-turn `/api/v1/ask` conversation history (ADR-019).
- Historical-outcome-based confidence calibration — Phase 5's backtest
  reports are the raw material for this, but the calibration itself needs
  Phase 6's review loop and a real sample of completed trades before any
  number is framed as a probability (docs/MODEL_GOVERNANCE.md).
- Full historical index-constituent/delisting reconstruction — out of
  scope for a fixed watchlist, not an index (ADR-025).
- Strategy-change comparison/approval workflow (Phase 6) — Phase 5 only
  produces one backtest report at a time, not a side-by-side comparison.
- Async/background execution for long-running backtests — the current
  universe/window runs fast enough synchronously (see docs/TEST_EVIDENCE.md
  for the actual measured wall-clock time).
