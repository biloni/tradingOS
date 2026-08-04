# API Contracts

**Phase 8 (current)** replaced the entire Phase 1-7 API surface with a
versioned, 12-area REST API against the new domain model (ADR-043/044). The
Phase 1-7 contracts (`/api/v1/symbols`, `/api/v1/paper-orders`,
`/api/v1/ask`, `/api/v1/backtests` (old shape), `/api/v1/strategy-versions`
(old shape)) are **retired** — their routers/schemas/services were deleted,
not deprecated in place. See "Historical: Phase 1-7 contracts" at the
bottom of this document for the record, and ADR-044 in `docs/DECISIONS.md`
for why. `GET /health` is unchanged and still unversioned.

## Conventions used across every area below

- **Money/quantity fields are JSON strings**, never numbers (ADR-031,
  carried over from Phase 7) — e.g. `"quantity": "0.10000000"`, never
  `0.1`. Every `Decimal`-backed Pydantic field renders this way
  automatically; verified by `tests/test_openapi_snapshot.py`.
- **Pagination** (list endpoints): `{"items": [...], "total": N, "limit":
  N, "offset": N}` (`schemas/common.py::Page[T]`). Query params `limit`
  (default 50, max 200) and `offset` (default 0).
- **Idempotency**: an optional `idempotency_key` string field, unique-
  constrained in the DB. A repeated request with the same key returns the
  original resource unchanged (`200`/`201`, never a duplicate row) — used
  by `POST /api/v1/orders`, `POST /api/v1/orders/import`, and (at the
  domain-model level, not yet exposed on a write endpoint)
  `cash_ledger`/`executions`/`job_runs`.
- **Optimistic concurrency**: a PATCH body carries `expected_updated_at`;
  the server `409`s if it doesn't match the row's current `updated_at`
  (used by `PATCH /api/v1/watchlists/items/{id}` and `PATCH
  /api/v1/alerts/{id}`).
- **Auth**: none (single-user, ADR-007) — every endpoint that needs "whose
  data is this" resolves the one seeded `user_profile` row via
  `core.dependencies.get_current_user_id()`.
- **Errors**: `404` (not found), `422` (validation / unresolvable
  reference), `409` (duplicate / stale-concurrency), `400` (invalid state
  transition, e.g. confirming an already-filled order) — always a JSON
  body `{"detail": "..."}` or FastAPI's standard `422` validation-error
  shape.

## 1. Instruments & symbol validation (`routers/instruments.py`)

- `GET /api/v1/instruments` — paginated list. Query: `active` (bool,
  optional), `q` (ticker/name substring, optional).
- `GET /api/v1/instruments/{instrument_id}` — detail. `404` if unknown.
- `GET /api/v1/instruments/{instrument_id}/validation-events` — that
  instrument's `instrument_validation_events` history (list, newest-first).
- `POST /api/v1/instruments/validate` — resolves a raw ticker string
  against `instruments`/`instrument_aliases`.

```json
// POST /api/v1/instruments/validate  ->  request
{"raw_input": "aapl"}
// 200 response
{
  "status": "RESOLVED",
  "instrument": {"id": "d4798467-...", "ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "EQUITY", "active": true},
  "reason": "Matched on ticker (case-insensitive)."
}
```
`status` is one of `RESOLVED\|AMBIGUOUS\|QUARANTINED`; `instrument` is
`null` unless `RESOLVED`. Every call writes an
`instrument_validation_events` row regardless of outcome.

## 2. Watchlists (`routers/watchlists.py`)

- `GET /api/v1/watchlists` — the caller's watchlists.
- `GET /api/v1/watchlists/{watchlist_id}/items` — paginated, filterable by
  `tier` (int) and `active` (bool), sortable via `sort=priority` /
  `sort=-priority`.
- `POST /api/v1/watchlists/{watchlist_id}/items` — add an instrument.
  `422` if `instrument_id` doesn't resolve; `409` if already a member.
- `PATCH /api/v1/watchlists/items/{item_id}` — partial update, requires
  `expected_updated_at` (optimistic concurrency, `409` on mismatch).

```json
// POST .../items -> request
{"instrument_id": "b7f9b54a-...", "tier": 2, "priority": 500}
// 201 response
{
  "id": "2ee1efca-...", "watchlist_id": "d75b2207-...",
  "instrument": {"id": "b7f9b54a-...", "ticker": "SPY", "name": "...", "exchange": "NYSE", "asset_type": "ETF", "active": true},
  "tier": 2, "priority": 500, "active": true, "notes": null,
  "monitoring_frequency": "DAILY", "added_at": "2026-08-03", "updated_at": "2026-08-03T22:33:31-07:00"
}
```

## 3. Market overview & data freshness (`routers/market.py`)

- `GET /api/v1/market/overview` — `{"regime": RegimeResponse|null,
  "tracked_instrument_count": int, "stale_instrument_count": int}`.
- `GET /api/v1/market/freshness` — one row per tracked instrument:
  `{"instrument_id", "ticker", "latest_bar_as_of", "latest_bar_ingested_at",
  "is_stale"}`.
- `GET /api/v1/market/instruments/{ticker}/bars` — `market_bars` history.
  Query: `start`/`end` (date, optional).
- `GET /api/v1/market/instruments/{ticker}/indicators` — latest
  `technical_indicator_snapshots` per indicator. Query: `as_of` (optional).

## 4. Recommendations & committee detail (`routers/recommendations.py`)

- `GET /api/v1/recommendations` — paginated, filterable by `status`
  (`RecommendationStatus`).
- `GET /api/v1/recommendations/{id}` — detail with `latest_version`
  (nested `RecommendationVersionResponse`, including `levels`).
- `GET /api/v1/recommendations/committee-sessions/{session_id}` — the full
  committee run: every `agent_runs` row (role, status, timing) with its
  `agent_opinions` row nested inline.

```json
// GET .../committee-sessions/{id}  (real seeded example, live-verified)
{
  "id": "61612c7b-...", "instrument": {"ticker": "AAPL", "...": "..."},
  "triggered_by": "PREMARKET_JOB", "status": "COMPLETED",
  "started_at": "2026-08-03T06:00:00-07:00", "completed_at": "2026-08-03T06:04:00-07:00",
  "agent_runs": [
    {"id": "...", "role": "BULL", "status": "SUCCEEDED", "started_at": "...", "completed_at": "...",
     "opinion": {"stance": "BULLISH", "structured_output": {"...": "..."}}},
    {"id": "...", "role": "BEAR", "status": "SUCCEEDED", "...": "...", "opinion": {"stance": "BEARISH", "...": "..."}}
  ]
}
```

## 5. Portfolio, positions, cash & risk (`routers/portfolio.py`)

- `GET /api/v1/portfolio/accounts` — the caller's accounts.
- `GET /api/v1/portfolio/accounts/{account_id}` — `account` +
  derived `cash` (`starting_cash + sum(cash_ledger.amount)`) + open
  `positions` + `latest_risk_snapshot`.

```json
{
  "account": {"id": "41d020ae-...", "account_type": "MANUAL", "name": "Personal Journal", "base_currency": "USD", "is_active": true},
  "cash": {"account_id": "41d020ae-...", "cash": "15831.500000", "starting_cash": "10000.000000"},
  "positions": [{"instrument": {"ticker": "AAPL", "...": "..."}, "quantity": "10.00000000", "avg_cost": "306.200000", "market_value": null}],
  "latest_risk_snapshot": {"as_of": "...", "gross_exposure_pct": "0.3040", "largest_position_pct": "0.3040", "sector_concentration": {"Technology": "0.3040"}, "correlation_flag": false}
}
```

## 6. Manual trade entry, order import, fills, reconciliation (`routers/orders.py`)

The largest area — the propose → confirm human-gate flow (ADR-014,
unchanged principle from the shipped MVP), plus bulk historical import and
the self-consistency reconciliation check.

- `GET /api/v1/orders` — paginated, filterable by `account_id`, `status`.
- `GET /api/v1/orders/{id}` — detail including nested `executions`.
- `POST /api/v1/orders` — propose. Creates a `DRAFT` order only — **no
  fill happens yet**. Accepts `idempotency_key`.
- `POST /api/v1/orders/{id}/confirm` — the human-confirmation gate. For a
  `MANUAL` account, fills immediately at `limit_price` (`422` if none
  given); for `PAPER_ALPACA`, only moves to `SUBMITTED` (no real broker
  call this pass). Books the `Execution`, updates `positions`/
  `position_lots` FIFO, and posts a `cash_ledger` entry, atomically.
- `POST /api/v1/orders/{id}/cancel` — `DRAFT`→`CANCELED` only.
- `POST /api/v1/orders/import` — bulk-backfill already-executed historical
  fills (`{"account_id", "fills": [...]}`) without the propose/confirm
  round trip — each fill immediately posts as `FILLED`. Idempotent per-fill.
- `GET /api/v1/orders/reconciliation/{account_id}` — one row per position:
  `positions.quantity` vs. `sum(position_lots.quantity_remaining)`, with a
  `discrepancy` column that must be `0` in normal operation.

```json
// POST /api/v1/orders -> request
{"account_id": "41d020ae-...", "instrument_id": "7c9c67fc-...", "side": "BUY", "order_type": "MARKET", "quantity": "5", "limit_price": "221.30"}
// 201 response (DRAFT — nothing filled yet)
{"id": "001387be-...", "account_id": "41d020ae-...", "instrument": {"ticker": "JPM", "...": "..."},
 "side": "BUY", "order_type": "MARKET", "time_in_force": "DAY", "quantity": "5.00000000",
 "limit_price": "221.300000", "status": "DRAFT", "submitted_at": null, "filled_at": null,
 "created_at": "2026-08-03T22:57:31-07:00", "executions": []}

// POST /api/v1/orders/{id}/confirm -> 200 response (now FILLED)
{"...": "same shape", "status": "FILLED", "filled_at": "2026-08-03T23:03:16-07:00",
 "executions": [{"id": "49fc3b78-...", "quantity": "5.00000000", "price": "221.300000", "executed_at": "2026-08-03T23:03:16-07:00"}]}

// GET /api/v1/orders/reconciliation/{account_id} -> 200
[{"account_id": "41d020ae-...", "instrument_id": "7c9c67fc-...", "ticker": "JPM",
  "position_quantity": "5.00000000", "lots_quantity": "5.00000000", "discrepancy": "0E-8"}]
```

## 7. Trade journal & reviews (`routers/journal.py`)

- `GET /api/v1/journal/trades` — paginated `trades`, each with nested
  `thesis`, `notes`, `reviews`.
- `GET /api/v1/journal/trades/{trade_id}` — detail (same shape).
- `POST /api/v1/journal/trades/{trade_id}/notes` — append a `trade_notes`
  row. `POST .../reviews` — append a `trade_reviews` row (`rating` +
  `review_text`, both optional). Both return the full updated trade detail.

## 8. Performance & benchmarks (`routers/performance.py`)

- `GET /api/v1/performance/accounts/{account_id}` — that account's
  `performance_snapshots` history.
- `GET /api/v1/performance/compare/{account_id}` — `{"account":
  PerformanceSnapshotResponse|null, "benchmark": BenchmarkSnapshotResponse|
  null}` for the most recent overlapping period.

## 9. Alerts (`routers/alerts.py`)

- `GET /api/v1/alerts` — paginated, filterable by `status`.
- `PATCH /api/v1/alerts/{alert_id}` — status transition (`OPEN` →
  `ACKNOWLEDGED`/`DISMISSED`), requires `expected_updated_at` (`409` on
  stale write) — guarded by `assert_transition_allowed` against
  `ALERT_TRANSITIONS`.

## 10. Daily plans (`routers/plans.py`)

- `GET /api/v1/plans/daily` — composed live on every call (no scheduler
  exists yet, ADR-040) from that day's `market_regime_snapshots`,
  `recommendations` opened that day, and the caller's `OPEN` alerts. Query:
  `as_of` (date, defaults to today).

## 11. Backtests (`routers/backtests.py`)

- `GET /api/v1/backtests` — paginated `backtest_runs`, newest-first, each
  with nested `trades` (`backtest_trades` rows, normalized from
  `results_summary.trades`).
- `GET /api/v1/backtests/{run_id}` — detail (same shape). Read-only this
  pass — `POST` (running a new backtest) is Phase 1-7 business logic
  explicitly out of Phase 8's "domain model, not full business logic"
  scope (ADR-044); the seed script populates realistic historical runs so
  this read surface has real data to serve today.

## 12. Settings & provider status (`routers/settings.py`)

- `GET /api/v1/settings/providers` — every `provider_config` row plus a
  derived `has_credential_configured` boolean (cross-referenced against
  which env vars are actually set) — **never the credential value itself**.
- `GET /api/v1/settings/investment-profile` — the caller's
  `investment_profile`.
- `GET /api/v1/settings/risk-policy` / `PATCH .../risk-policy` — read/update
  the numeric risk limits (`risk_budget_pct`, `max_position_pct`,
  `max_sector_pct`, `max_correlation`, `speculative_position_pct_cap`).
  Every field in the PATCH body is optional — only provided fields change.

## Authorization assumptions

No auth exists (ADR-007) — every request is implicitly "the one user."
Endpoints that resolve `owner_user_id` do so via
`core.dependencies.get_current_user_id()`, which raises a `500` (not a
silent wrong-user read) if no `user_profile` row exists — the seed script
(`tradingos-seed`) is a hard prerequisite for the API to serve any
owner-scoped data. A future multi-user phase replaces this one dependency
with real session auth; no router code changes, since every query already
filters by `owner_user_id`.

## Historical: Phase 1-7 contracts (retired, ADR-044)

The shipped MVP exposed `GET /health` (kept, unversioned), `GET
/api/v1/symbols`, `GET /api/v1/symbols/{ticker}/bars`, `GET
/api/v1/symbols/{ticker}/indicators`, the `/api/v1/paper-orders*` propose/
confirm/refresh/cancel flow, `GET /api/v1/portfolio` (+ `/reconciliation`),
`POST /api/v1/ask`, `POST /api/v1/backtests` (+ list/detail), and the
`/api/v1/strategy-versions*` propose/compare/approve/reject flow — full
request/response shapes for all of these are preserved below exactly as
written during Phases 1-7, for the historical record. Every one of these
routers/schemas/services was deleted in Phase 8 (not deprecated in place);
none of the URLs below resolve on the current API.

### `GET /api/v1/symbols`

No query params. Returns every seeded symbol.

**Response `200`**
```json
[
  {"id": 1, "ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "EQUITY", "active": true}
]
```

### `GET /api/v1/symbols/{ticker}/bars`

**Query params:** `start` (date, optional, default: `end - 90 days`), `end`
(date, optional, default: today). Returns the latest (max-`fetched_at`)
`PriceBar` row per date in range — see `services/price_bars.py`.

**Response `200`** — money fields are strings (`Numeric(18,6)`, full stored
precision — never a JSON float; see docs/SECURITY.md / engineering rules on
currency):
```json
[
  {
    "as_of": "2026-07-31",
    "open": "304.810000", "high": "310.690000", "low": "300.000000", "close": "308.910000",
    "volume": 132756799,
    "source": "alpaca", "adjustment": "split",
    "fetched_at": "2026-08-03T07:23:39.309827-07:00"
  }
]
```

**Response `404`** if `ticker` isn't in the seeded `Symbol` table.

### `GET /api/v1/symbols/{ticker}/indicators`

**Query params:** `as_of` (date, optional — defaults to the most recent date
that has any indicator row for this symbol). Returns every indicator value
computed for that one date (up to 12 rows — one per `IndicatorName`).

**Response `200`**
```json
[
  {"as_of": "2026-07-31", "indicator_name": "RSI_14", "version": "v1", "value": "43.243931", "computed_at": "2026-08-03T07:23:39.485828-07:00"}
]
```

**Response `404`** if `ticker` isn't in the seeded `Symbol` table. Returns
`[]` (not 404) if the symbol exists but has no indicators computed yet for
the requested/default date.

### `POST /api/v1/paper-orders`

Step 1 of 2 (ADR-014, principle 11) — proposes a `DRAFT` order. **Nothing is
sent to Alpaca.** Validates capital sufficiency (BUY) or held-quantity
sufficiency (SELL, no shorting).

**Request body**
```json
{"ticker": "SPY", "side": "BUY", "quantity": 1, "order_type": "MARKET", "limit_price": null}
```

**Response `201`** — a `DRAFT` order (see `GET .../{id}` below for the full shape).

**Response `400`** — insufficient cash/position, with a plain-English `detail`.
**Response `404`** — unknown `ticker`.

### `POST /api/v1/paper-orders/{id}/confirm`

Step 2 of 2 (ADR-014) — the explicit human-confirmation action. Only a
`DRAFT` order can be confirmed. Re-validates capital/position immediately
before submitting (prices/positions may have moved since propose), then
calls `AlpacaPaperBrokerProvider.submit_paper_order()`. Since fills are
asynchronous (ADR-016 — confirmed live against a real order), this also
does one immediate re-check if the submit response isn't yet terminal.

**Response `200`**
```json
{
  "id": 1, "portfolio_id": 1, "ticker": "SPY", "side": "BUY", "quantity": 1,
  "filled_quantity": 1, "order_type": "MARKET", "limit_price": null,
  "status": "FILLED", "broker_order_id": "cc95fe9c-...",
  "filled_avg_price": "754.920000", "filled_at": "2026-08-03T07:54:56.905294-07:00",
  "submitted_at": "2026-08-03T07:54:56.101910-07:00", "created_at": "2026-08-03T07:54:43.912262-07:00"
}
```

**Response `400`** — order isn't `DRAFT` (already confirmed, or canceled),
or capital/position no longer sufficient.

### `POST /api/v1/paper-orders/{id}/refresh`

Re-syncs status/fill fields from Alpaca for an order still
`SUBMITTED`/`PARTIALLY_FILLED` (ADR-016). A future UI would poll this for
any open order.

**Response `200`** — the updated order (same shape as `confirm`).
**Response `400`** — order is already terminal (`FILLED`/`CANCELED`/`REJECTED`),
or has no `broker_order_id` yet.

### `POST /api/v1/paper-orders/{id}/cancel`

Cancels a `DRAFT` locally, or a `SUBMITTED` order via Alpaca's cancel
endpoint. **Response `400`** if the order is already terminal.

### `GET /api/v1/paper-orders` / `GET /api/v1/paper-orders/{id}`

List / detail. Same shape as `confirm`'s response.

### `GET /api/v1/portfolio`

**Response `200`**
```json
{
  "cash_usd": "9245.080000",
  "positions": [
    {"ticker": "SPY", "quantity": 1, "avg_entry_price": "754.920000",
     "current_price": "747.030000", "market_value": "747.030000", "unrealized_pl": "-7.890000"}
  ],
  "total_market_value": "747.030000", "total_equity": "9992.110000"
}
```
`current_price` comes from Phase 2's `get_latest_price_bars()` — the most
recent daily close, not a live quote (this app doesn't do intraday).

### `GET /api/v1/portfolio/reconciliation`

Phase 3's explicit reconciliation deliverable — our derived positions vs.
Alpaca's own paper-account position report.

**Response `200`**
```json
[{"ticker": "SPY", "our_quantity": 1, "alpaca_quantity": "1", "discrepancy": "0"}]
```
A nonzero `discrepancy` means something diverged between our fill records
and Alpaca's book — worth investigating, not expected in normal operation.

### `POST /api/v1/ask`

The Phase 4 NL query entrypoint (ADR-019). Synthesis/explanation only —
grounded in tool results executed against the deterministic data model
(`services/llm_tools.py`), never text-to-SQL, never the source of numeric
truth (principles 6/7). Rate-limited server-side: a 5-request burst, 5/min
steady-state refill, shared across the whole (single-user) process
(ADR-021).

**Request body**
```json
{"question": "What does AAPL's current setup look like?"}
```
`question` must be 1–2000 characters.

**Response `200`**
```json
{
  "answer": "AAPL's SMA_20 is above its SMA_50 and RSI_14 is in the bullish 50-70 band...",
  "recommendations": [
    {
      "recommendation_id": 1,
      "symbol_ticker": "AAPL",
      "score": "75.00",
      "confidence": "MEDIUM",
      "signal_breakdown": {"trend": 1, "momentum": 1, "macd": 1, "bollinger": -1}
    }
  ],
  "llm_call_log_ids": [1, 2],
  "iterations": 2
}
```
`recommendations` is only non-empty if the model called
`compute_recommendation` during this request (ADR-018) — a purely
informational question (e.g. "what's AAPL's RSI?") returns an empty list.
`llm_call_log_ids` lets a caller look up the exact token counts/cost for
every underlying Anthropic call this request made.

**Response `422`** — `question` is empty or over 2000 characters.

**Response `429`** — rate limit exceeded; retry after a few seconds.

**Response `503`** — `ANTHROPIC_API_KEY` is not configured (principle 5:
graceful degradation, not a crash).

### `POST /api/v1/backtests` (old shape)

Runs a historical replay of the scoring engine synchronously (ADR-022..025)
and returns the full report — no polling, no background job. Every field
is optional.

**Request body**
```json
{
  "date_range_start": "2024-08-01",
  "date_range_end": "2026-08-01",
  "strategy_version_id": null,
  "entry_score_threshold": "65",
  "exit_score_threshold": "40",
  "max_holding_days": 10,
  "position_size_pct": "0.10",
  "starting_cash": "10000.00",
  "benchmark_ticker": "SPY"
}
```
`date_range_start`/`date_range_end` default to the full ~2-year ingested
history when omitted. `strategy_version_id` defaults to the currently
active `StrategyVersion` — passing an explicit id lets Phase 6 backtest a
not-yet-approved candidate version without a schema change.

**Response `201`**
```json
{
  "id": 1,
  "strategy_version_id": 1,
  "date_range_start": "2024-08-01",
  "date_range_end": "2026-08-01",
  "parameters": {
    "entry_score_threshold": "65", "exit_score_threshold": "40",
    "max_holding_days": 10, "position_size_pct": "0.10",
    "starting_cash": "10000.00", "benchmark_ticker": "SPY"
  },
  "results_summary": {
    "ending_equity": "11250.400000", "total_return_pct": "12.50",
    "max_drawdown_pct": "8.30", "win_rate_pct": "55.00", "num_trades": 42,
    "avg_win_pct": "6.20", "avg_loss_pct": "-3.10",
    "benchmark_return_pct": "9.80",
    "equity_curve": [{"as_of": "2024-08-01", "equity": "10000.000000"}],
    "trades": [
      {"ticker": "AAPL", "entry_date": "2024-09-03", "entry_price": "180.500000",
       "exit_date": "2024-09-13", "exit_price": "191.200000", "quantity": 5,
       "pnl_usd": "53.500000", "pnl_pct": "5.93", "exit_reason": "SIGNAL_EXIT"}
    ]
  },
  "created_at": "2026-08-03T12:00:00+00:00"
}
```
`benchmark_return_pct` is `null` if `benchmark_ticker` has no price history
in range (never an error — the benchmark is a nullable bonus in the
report, not a required input). `exit_reason` is one of `SIGNAL_EXIT`,
`MAX_HOLDING_DAYS`, `END_OF_BACKTEST` (a position still open when the
window ends, force-closed at the last known close — not a real signal).

**Response `400`** — `strategy_version_id` doesn't exist, the date range is
invalid, or no symbol has any price history in the requested range.

### `GET /api/v1/backtests` / `GET /api/v1/backtests/{id}` (old shape)

List (newest-first) / detail. Same shape as the `POST` response.

### `POST /api/v1/strategy-versions`

Propose a candidate scoring configuration (ADR-026 — a user/operator-
submitted candidate, not an autonomous optimizer). Never touches the
currently active version.

**Request body**
```json
{
  "name": "Tighter RSI band",
  "config": {
    "weights": {"trend": 1.0, "momentum": 1.5, "macd": 1.0, "bollinger": 1.0},
    "rsi_bullish_low": 55, "rsi_bullish_high": 65, "rsi_oversold": 30
  }
}
```
`config` is validated against the exact shape `services/scoring.py`'s
`compute_score()` understands — a malformed shape or `rsi_bullish_low >=
rsi_bullish_high` is a `422`, not a silently-broken (always-neutral) score.

**Response `201`**
```json
{
  "id": 2, "name": "Tighter RSI band", "config": {"...": "..."},
  "status": "PROPOSED", "decided_at": null, "decision_comment": null,
  "created_at": "2026-08-03T12:00:00+00:00"
}
```

### `POST /api/v1/strategy-versions/{id}/compare`

Read-only and repeatable (ADR-028) — runs a fresh backtest for both the
candidate and the currently active version with **identical** parameters
(same optional overrides as `POST /api/v1/backtests`, minus
`strategy_version_id`), persisting two real `BacktestRun` rows every call.
Never changes the candidate's `status`.

**Response `200`**
```json
{
  "candidate_backtest": { "...": "full BacktestRunOut, see POST /api/v1/backtests" },
  "active_backtest": { "...": "full BacktestRunOut" },
  "delta": {
    "total_return_pct": "3.20", "max_drawdown_pct": "-1.10",
    "win_rate_pct": "2.50", "avg_win_pct": "0.40", "avg_loss_pct": "-0.15",
    "num_trades": 12
  }
}
```
`delta` is candidate minus active for each metric — surfaced for a human
to read, never used by the system to auto-decide anything.

**Response `404`** — unknown candidate id.

### `POST /api/v1/strategy-versions/{id}/approve`

The explicit human approval action (principle 16) — requires the
candidate to be `PROPOSED`. Re-runs the comparison itself (ADR-028, never
trusts a prior `/compare` call) to produce the audit snapshot, then
activates the candidate and supersedes the previously active version.

**Request body** — same optional params as `/compare`, plus:
```json
{"comment": "Backtested better win rate with similar drawdown, approving."}
```

**Response `200`** — the candidate, now `ACTIVE`:
```json
{
  "id": 2, "name": "Tighter RSI band", "config": {"...": "..."},
  "status": "ACTIVE", "decided_at": "2026-08-03T12:05:00+00:00",
  "decision_comment": "Backtested better win rate with similar drawdown, approving.",
  "created_at": "2026-08-03T12:00:00+00:00"
}
```
The previously active version's `status` becomes `SUPERSEDED` (kept for
history). One `AuditEvent` (`record_type="STRATEGY_VERSION_APPROVED"`)
records both backtest ids, the delta, and the comment.

**Response `400`** — candidate isn't `PROPOSED` (already decided).
**Response `404`** — unknown candidate id.

### `POST /api/v1/strategy-versions/{id}/reject`

**Request body**: `{"comment": "..."}` (optional). Requires `PROPOSED`. No
backtest re-run — nothing to activate.

**Response `200`** — the candidate, now `REJECTED`, with `decided_at`/
`decision_comment` set. **Response `400`** — not `PROPOSED`.

### `GET /api/v1/strategy-versions` / `GET /api/v1/strategy-versions/{id}`

List (newest-first) / detail. Same shape as `POST /api/v1/strategy-versions`.
