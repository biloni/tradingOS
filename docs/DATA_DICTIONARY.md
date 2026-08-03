# Data Dictionary

This documents the **conceptual** data model for the whole system so it can
be reviewed end-to-end. Entities not yet implemented say so; implemented ones
say which migration/module they live in. As of Phase 2: `Symbol`,
`PriceBar`, `Indicator` are live (migration `bd027d9f35a2`); everything else
below is still conceptual, landing in the phase noted.

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

## Model inferences (Phase 4)

### Recommendation
`symbol`, `generatedAt`, `promptVersion`, `modelResponseRaw`,
`deterministicScoreInputs` (a snapshot of the Indicator values that fed the
score, for audit), `rationale` (grounded in tool results only), `confidence`
(a calibrated value — see docs/MODEL_GOVERNANCE.md — not the LLM's
self-reported number), `status`.

### StrategyVersion
A versioned, user-approved configuration of scoring formulas/thresholds
(principle 8). Strategy changes are proposed, backtested, and require
explicit approval before a new version activates (principle 16).

### LLMCallLog
`promptVersion`, `model`, `inputTokens`, `outputTokens`, `costUsd`,
`requestPayload`, `responsePayload`, `createdAt`. Every LLM call is logged
here for cost tracking and auditability (principle 8/9) — no exceptions.

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

## Backtesting (Phase 5)

### BacktestRun
`strategyVersionId`, `dateRangeStart`, `dateRangeEnd`, `resultsSummary
(JSON)`, `createdAt`. Runs against historical `PriceBar` data with realistic
fills — no look-ahead bias, no survivorship bias (principle 14): the symbol
universe for a given historical date must be reconstructable as it existed
on that date, not filtered by today's index membership.

## Explicitly not modeled

- **Live orders** — no `LiveOrder` entity exists anywhere in this dictionary
  (principle 10). If a future phase adds live trading, it gets its own
  explicitly-named entity and interface, not a repurposed `PaperOrder`.
- **User/auth tables** — single-user system (ADR-007).
