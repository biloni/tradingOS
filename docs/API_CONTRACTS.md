# API Contracts

Versioning convention for future endpoints: `/api/v1/...`. The only endpoint
that exists as of Phase 1 predates that convention (see note below) and will
be the one exception.

## `GET /health`

No auth (single-user system, ADR-007). No query params.

**Response `200`**
```json
{
  "status": "ok",
  "time_utc": "2026-08-03T13:41:00.416286+00:00"
}
```

Used by `apps/web`'s home page to show a live API-reachability indicator
(see `lib/api-client.ts`, `app/page.tsx`).

**Note on versioning:** `/health` is intentionally unversioned — health
checks are an infrastructure concern, not a product API surface, and
conventionally live outside a version prefix (matches common practice for
load balancer / uptime-check endpoints). Every endpoint added from Phase 2
onward uses `/api/v1/...`.

## `GET /api/v1/symbols`

No query params. Returns every seeded symbol.

**Response `200`**
```json
[
  {"id": 1, "ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "EQUITY", "active": true}
]
```

## `GET /api/v1/symbols/{ticker}/bars`

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

## `GET /api/v1/symbols/{ticker}/indicators`

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

## `POST /api/v1/paper-orders`

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

## `POST /api/v1/paper-orders/{id}/confirm`

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

## `POST /api/v1/paper-orders/{id}/refresh`

Re-syncs status/fill fields from Alpaca for an order still
`SUBMITTED`/`PARTIALLY_FILLED` (ADR-016). A future UI would poll this for
any open order.

**Response `200`** — the updated order (same shape as `confirm`).
**Response `400`** — order is already terminal (`FILLED`/`CANCELED`/`REJECTED`),
or has no `broker_order_id` yet.

## `POST /api/v1/paper-orders/{id}/cancel`

Cancels a `DRAFT` locally, or a `SUBMITTED` order via Alpaca's cancel
endpoint. **Response `400`** if the order is already terminal.

## `GET /api/v1/paper-orders` / `GET /api/v1/paper-orders/{id}`

List / detail. Same shape as `confirm`'s response.

## `GET /api/v1/portfolio`

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

## `GET /api/v1/portfolio/reconciliation`

Phase 3's explicit reconciliation deliverable — our derived positions vs.
Alpaca's own paper-account position report.

**Response `200`**
```json
[{"ticker": "SPY", "our_quantity": 1, "alpaca_quantity": "1", "discrepancy": "0"}]
```
A nonzero `discrepancy` means something diverged between our fill records
and Alpaca's book — worth investigating, not expected in normal operation.

## `POST /api/v1/ask`

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

## `POST /api/v1/backtests`

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

## `GET /api/v1/backtests` / `GET /api/v1/backtests/{id}`

List (newest-first) / detail. Same shape as the `POST` response.

## `POST /api/v1/strategy-versions`

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

## `POST /api/v1/strategy-versions/{id}/compare`

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

## `POST /api/v1/strategy-versions/{id}/approve`

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

## `POST /api/v1/strategy-versions/{id}/reject`

**Request body**: `{"comment": "..."}` (optional). Requires `PROPOSED`. No
backtest re-run — nothing to activate.

**Response `200`** — the candidate, now `REJECTED`, with `decided_at`/
`decision_comment` set. **Response `400`** — not `PROPOSED`.

## `GET /api/v1/strategy-versions` / `GET /api/v1/strategy-versions/{id}`

List (newest-first) / detail. Same shape as `POST /api/v1/strategy-versions`.

## Phase 7 — frontend consumer

Every endpoint contract above is now consumed by `apps/web`
(`lib/api/*.ts`, one module per domain, response fields typed
field-for-field against these contracts — see ADR-031 on the
Decimal-as-string convention). No new endpoints were added this phase;
Phase 7 was UI-only against the API surface documented above.
