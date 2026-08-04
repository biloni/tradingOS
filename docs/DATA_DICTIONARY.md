# Data Dictionary

This documents the **conceptual** data model for the whole system so it can
be reviewed end-to-end. Entities not yet implemented say so; implemented ones
say which migration/module they live in. As of Phase 6: every entity below
is live. Phase 6 added no new entity — it added a review/approval
*process* (a real lifecycle on `StrategyVersion`, plus reusing
`BacktestRun`) rather than a new table.

## Dimensions (master data — **implemented, Phase 2**)

### Symbol
`apps/api/src/tradingos_api/models/symbol.py`. The tradable instrument.
`id`, `ticker` (unique), `name`, `exchange`, `asset_type` (native Postgres
enum: `EQUITY | ETF` — ADR-003), `active`. Seeded from
`seed_symbols.py` (~25 liquid equities + SPY/QQQ/IWM/DIA).

### FxRate / currency
Not applicable in the current scope — Alpaca US equities/ETFs are USD-only,
unlike the multi-currency concern in other Workday-style HR systems. No
currency-conversion table exists in this data model.

## Facts (immutable, append-only — **implemented, Phase 2**)

### PriceBar
`apps/api/src/tradingos_api/models/price_bar.py`. One row per `(symbol_id,
as_of, timeframe)` — but that tuple is **not** a unique constraint (ADR-011):
`open, high, low, close` (`Numeric(18,6)`), `volume` (`BigInteger`),
`source` ("alpaca"), `adjustment` ("split" — ADR-010), `fetched_at`
(tz-aware). Never mutated — a correction is a new row with a later
`fetched_at`, not an update in place. `services/price_bars.py`'s
`get_latest_price_bars()` is the one shared helper that derives "current"
from this append-only table (every future caller reads through it, never
re-implements the max-`fetched_at`-per-date logic itself).

## Deterministic calculations (**implemented, Phase 2**)

### Indicator
`apps/api/src/tradingos_api/models/indicator.py`. Derived from `PriceBar` by
a versioned, plain-Python formula (`services/indicators.py`): `SMA_20`,
`SMA_50`, `EMA_12`, `EMA_26`, `RSI_14`, `MACD_LINE`, `MACD_SIGNAL`,
`MACD_HIST`, `BB_UPPER`, `BB_MID`, `BB_LOWER`, `ATR_14`. `symbol_id`,
`as_of`, `indicator_name`, `version` (currently `"v1"`), `value`
(`Numeric(18,6)`). Unlike `PriceBar`, this **is** idempotent — unique
constraint on `(symbol_id, as_of, indicator_name, version)` — since it's a
pure function of existing facts, not a new observation (ADR-012).

## Model inferences (**implemented, Phase 4** — migration `cd811cf4102b`)

### StrategyVersion
`apps/api/src/tradingos_api/models/strategy_version.py`. A versioned
configuration of scoring weights/thresholds (principle 8 — never
hardcoded): `id`, `name`, `config` (JSON —
`{"weights": {...}, "rsi_bullish_low", "rsi_bullish_high", "rsi_oversold"}`),
`status` (native enum `PROPOSED|ACTIVE|REJECTED|SUPERSEDED` — **implemented,
Phase 6**, migration `eed7cb451bdc`, replacing the earlier `is_active: bool`
outright, ADR-027), `decided_at` / `decision_comment` (nullable — set once
when a `PROPOSED` version is approved or rejected), `created_at`. The MVP's
first version is lazily created directly as `ACTIVE` by
`services/strategy.py`'s `get_or_create_default_strategy_version()` — it
skips the approval gate since it's the first version, not a proposed
change. Every subsequent change goes through Phase 6's propose → compare →
approve/reject flow (principle 16, ADR-026/028):
`propose_strategy_version()`, `run_comparison()`,
`approve_strategy_version()`, `reject_strategy_version()` — exactly one
`ACTIVE` row at a time; approving a candidate flips the previously active
row to `SUPERSEDED` (kept for history, same pattern as
`RecommendationStatus`).

### Recommendation
`apps/api/src/tradingos_api/models/recommendation.py`. `id`, `symbol_id`
(FK), `strategy_version_id` (FK), `generated_at`, `prompt_version`,
`model_response_raw` (Text), `score` (`Numeric(6,2)`, computed by
`services/scoring.py` — never by the LLM, principle 6),
`deterministic_score_inputs` (JSON snapshot of the 4 signal values that fed
the score, for audit), `confidence` (native enum `LOW|MEDIUM|HIGH` — a
deterministic band computed in code from signal agreement, never the LLM's
self-reported number — principle 15, docs/MODEL_GOVERNANCE.md), `rationale`
(Text — the LLM's synthesis, grounded only in tool results), `status`
(native enum `ACTIVE|SUPERSEDED` — a recompute for the same symbol
supersedes the prior row rather than deleting it, same append-history
philosophy as `PaperOrder`'s status transitions).

### LLMCallLog
`apps/api/src/tradingos_api/models/llm_call_log.py`. `id`, `prompt_version`,
`model`, `input_tokens`, `output_tokens`, `cost_usd` (`Numeric(10,6)`,
computed by `services/llm_cost.py`'s `estimate_cost_usd()` from a
documented, versioned per-token pricing constant), `request_payload` /
`response_payload` (JSON — the full messages/tools sent and the raw content
blocks + stop_reason received), `created_at`. Written once per Anthropic API
call from `services/ask.py`'s orchestration loop — a single
`/api/v1/ask` request can produce several rows if the tool-use loop takes
multiple turns (capped at 5, ADR-019) — no exceptions (principle 8/9).

`PaperOrder.linked_recommendation_id` (nullable FK to `Recommendation`) was
added this phase now that `Recommendation` exists — see
`apps/api/src/tradingos_api/models/paper_order.py`. Not yet set by any
code path (no UI exists to link a paper order back to the recommendation
that prompted it); the column exists so a future phase can wire it without
another migration.

## Transactions (user decisions — **implemented, Phase 3**)

### PaperPortfolio
`apps/api/src/tradingos_api/models/paper_portfolio.py`. One row (the MVP has
exactly one, lazily created — ADR-013). `starting_cash_usd`
(`Numeric(18,2)`, default 10,000.00), `created_at`. Current cash is **never**
stored — `services/portfolio.py`'s `get_derived_cash()` computes it from
`starting_cash_usd` plus/minus every filled `PaperOrder`.

### PaperPosition
**Not a table** (ADR-013). `services/portfolio.py`'s `get_derived_positions()`
computes net quantity and a weighted-average entry price (not FIFO/LIFO tax
lots — a documented MVP simplification) from filled `PaperOrder` rows, on
every read — mirrors the "current state is a derived view" pattern already
used for `PriceBar` (ADR-011).

### PaperOrder
`apps/api/src/tradingos_api/models/paper_order.py`. The user's actual
paper-trading activity. `portfolio_id`, `symbol_id`, `side` (BUY|SELL),
`quantity`, `order_type` (MARKET|LIMIT), `limit_price?`, `status` (DRAFT →
SUBMITTED → FILLED/PARTIALLY_FILLED/CANCELED/REJECTED — ADR-014),
`filled_quantity` (separate from `quantity` to correctly represent a
partial fill), `broker_order_id` (Alpaca's own order id, set only after
`confirm`), `filled_avg_price?`, `filled_at?`, `submitted_at?`,
`created_at`. `linked_recommendation_id` is intentionally **not** a column
yet — `Recommendation` doesn't exist until Phase 4; it lands then, alongside
the entity it actually references.

### AuditEvent (the audit trail — principle 9 — **implemented, Phase 3**)
`apps/api/src/tradingos_api/models/audit_event.py`. `record_type`, `ref_id`
(plain integer, not a FK — ADR-015), `snapshot` (JSON — native `JSONB` on
Postgres, portable `JSON` elsewhere via SQLAlchemy's dialect-variant
pattern, so in-memory SQLite tests still work), `created_at`. Written only
through `services/audit.py`'s `record_audit_event()`, for every paper-order
propose/confirm/refresh/cancel so far. Append-only; nothing here is ever
updated or deleted.

## Backtesting (**implemented, Phase 5** — migration `130bfdd45919`)

### BacktestRun
`apps/api/src/tradingos_api/models/backtest_run.py`. `id`,
`strategy_version_id` (FK), `date_range_start` / `date_range_end` (`Date`),
`parameters` (JSON — a full snapshot of every input: `entry_score_threshold`,
`exit_score_threshold`, `max_holding_days`, `position_size_pct`,
`starting_cash`, `benchmark_ticker` — these aren't part of
`StrategyVersion.config`, which only holds scoring weights, so they're
snapshotted here for full reproducibility, principle 8/9),
`results_summary` (JSON — `ending_equity`, `total_return_pct`,
`max_drawdown_pct`, `win_rate_pct`, `num_trades`, `avg_win_pct`,
`avg_loss_pct`, `benchmark_return_pct` (nullable), `equity_curve`, `trades`
— see `schemas/backtest.py` for the typed shape callers see), `created_at`.
Runs synchronously — `services/backtest.py`'s `run_backtest_simulation()`
(pure, no DB — see its module docstring) replays the scoring engine
day-by-day against real `PriceBar`/`Indicator` history with realistic
next-bar-open fills, no look-ahead bias (ADR-022), and no survivorship bias
(ADR-025 — the universe is every known `Symbol` regardless of today's
`active` flag). Never writes `PaperOrder` rows (ADR-024) — a backtest is a
historical simulation, not a real user action.

## Explicitly not modeled

- **Live orders** — no `LiveOrder` entity exists anywhere in this dictionary
  (principle 10). If a future phase adds live trading, it gets its own
  explicitly-named entity and interface, not a repurposed `PaperOrder`.
- **User/auth tables** — single-user system (ADR-007).
