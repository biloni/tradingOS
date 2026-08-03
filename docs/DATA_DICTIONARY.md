# Data Dictionary

This documents the **conceptual** data model for the whole system so it can
be reviewed end-to-end, even though most of these entities are implemented in
later phases (none exist as SQLAlchemy models or migrations yet — Phase 1 has
zero domain tables, see docs/ARCHITECTURE.md). Each entity below states which
phase implements it.

## Dimensions (master data — Phase 2)

### Symbol
The tradable instrument. `ticker`, `name`, `exchange`, `assetType (EQUITY |
ETF — ADR-003)`, `active`.

### FxRate / currency
Not applicable in the current scope — Alpaca US equities/ETFs are USD-only,
unlike the multi-currency concern in other Workday-style HR systems. No
currency-conversion table exists in this data model.

## Facts (immutable, append-only — Phase 2)

### PriceBar
One row per `(symbol, date, timeframe)`. `open, high, low, close, volume`,
`source` (e.g. "alpaca-iex"), `fetchedAt`, `timezone`. Never mutated — a
correction is a new row with a later `fetchedAt`, not an update in place
(principle: separate observed facts from everything else).

## Deterministic calculations (Phase 2)

### Indicator
Derived from `PriceBar` by a versioned, plain-Python formula (e.g., RSI-14,
SMA-50). `symbol`, `asOf`, `indicatorName`, `version`, `value`. Recomputable
from facts at any time — never hand-edited.

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

## Transactions (user decisions — Phase 3)

### PaperPortfolio
One row per configurable paper portfolio. `startingCashUsd` (default 10,000),
`currentCashUsd` (derived), `createdAt`.

### PaperPosition
Current holdings, derived from the sum of filled `PaperOrder` rows for a
symbol — never hand-edited, always recomputable (mirrors the "current state
is a derived view over immutable events" pattern used elsewhere in this
project's design language).

### PaperOrder / Trade
The user's actual paper-trading activity. `symbol`, `side`, `quantity`,
`orderType`, `limitPrice?`, `brokerOrderId` (from Alpaca's paper API),
`status`, `filledAvgPrice?`, `filledAt?`, `linkedRecommendationId?` (so
performance can be traced back to the recommendation that prompted it, or
null if the user placed it independently).

### AuditEvent (the audit trail — principle 9)
`recordType`, `refId`, `snapshot (JSON)`, `createdAt`. Written for every
recommendation, score, input snapshot, prompt version, model response, user
action, order, and override. Append-only; nothing here is ever updated or
deleted.

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
