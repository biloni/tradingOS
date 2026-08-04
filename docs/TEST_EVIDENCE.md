# Test Evidence

## Phase 1 — Foundations & Architecture (2026-08-03)

### Database

PostgreSQL 16.14, native Windows install (`winget install PostgreSQL.PostgreSQL.16`).
Verified running and reachable:

```
$ Get-Service -Name "*postgresql*"
Name               Status DisplayName
----               ------ -----------
postgresql-x64-16 Running postgresql-x64-16

$ psql -U tradingos_app -h localhost -d tradingos -c "SELECT current_user, current_database();"
 current_user  | current_database
---------------+------------------
 tradingos_app | tradingos
```

Docker Compose path (`infra/docker-compose.yml`) written and documented but
not exercised on this machine — native install is primary (ADR-008).

### `apps/api`

```
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
20 files already formatted

$ uv run mypy .
Success: no issues found in 19 source files

$ uv run pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 1 item

tests/test_health.py::test_health_returns_ok PASSED                      [100%]

============================== 1 passed in 0.33s ==============================
```

Dev server manually verified:
```
$ uv run uvicorn tradingos_api.main:app --port 8000
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000

$ curl http://localhost:8000/health
{"status":"ok","time_utc":"2026-08-03T13:41:00.416286+00:00"}
```

### `apps/web`

```
$ pnpm lint
$ eslint
(no output = no errors)

$ pnpm typecheck
$ tsc --noEmit
(no output = no errors)

$ pnpm test
$ vitest run
 RUN  v4.1.10
 Test Files  1 passed (1)
      Tests  1 passed (1)
```

### End-to-end browser check

Both dev servers running (`uv run uvicorn ...` on :8000, `pnpm dev` on
:3000). Loaded http://localhost:3000 in the Browser tool:

- Page text confirmed: "TradingOS" heading, mission tagline, and
  **"API status: ok (as of 2026-08-03T13:51:24.436777+00:00)"** — proving
  the web app successfully called the live API over HTTP.
- Console messages: only informational React DevTools/HMR-connected logs.
  **Zero errors or warnings.**

### Secrets check before commit

Confirmed no `.env` or `.env.local` files are staged (`.gitignore` covers
both patterns at any depth); only `.env.example` and `.env.local.example`
(placeholders) are tracked.

## Phase 2 — Data Ingestion & Indicators (2026-08-03)

### Migration round-trip

```
$ uv run alembic upgrade head
INFO  Running upgrade  -> bd027d9f35a2, create symbols, price_bars, indicators

$ uv run alembic downgrade base
INFO  Running downgrade bd027d9f35a2 -> , create symbols, price_bars, indicators

$ uv run alembic upgrade head
INFO  Running upgrade  -> bd027d9f35a2, create symbols, price_bars, indicators
```
Clean on the second pass — the first attempt (before a fix) failed with
`psycopg.errors.DuplicateObject: type "asset_type" already exists`, because
`op.drop_table()` doesn't drop the native Postgres ENUM types it created.
Fixed by adding explicit `sa.Enum(...).drop(...)` calls to the migration's
`downgrade()`.

### `apps/api` full suite

```
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
37 files already formatted

$ uv run mypy .
Success: no issues found in 36 source files

$ uv run pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 23 items

tests/test_alpaca_market_data.py .....                                   [ 21%]
tests/test_health.py .                                                   [ 26%]
tests/test_indicators.py .............                                  [ 82%]
tests/test_symbols_endpoints.py ....                                    [100%]

======================== 23 passed, 1 warning in 2.38s =========================
```
(The one warning is a third-party `DeprecationWarning` from `alpaca-py`'s
own `websockets.legacy` import — not our code, not actionable here.)

Indicator tests (13) use hand-verifiable invariants (constant series ->
SMA/EMA/Bollinger collapse to the constant, MACD = 0, ATR = 0; a hand-
computed 5-point series for exact SMA/EMA values; RSI all-gains/all-losses/
flat edge cases) rather than possibly-misremembered textbook reference
numbers. Provider tests (5) mock `alpaca-py`'s client — no network, no
credentials. Endpoint tests (4) run against an in-memory SQLite database
with a fake dataset — no live Postgres.

### Live ingestion run (real Alpaca data — user provided paper-trading keys)

```
$ uv run python -m tradingos_api.scripts.ingest_prices
Upserted 30 symbols.
AAPL: inserted 499 price bars.
AAPL: computed 5709 new indicator rows.
... (30 symbols total)
```

Database row counts after the run, confirmed via `psql`:

```
$ psql -U tradingos_app -h localhost -d tradingos -c "SELECT count(*) FROM symbols;"
    30
$ psql ... -c "SELECT count(*) FROM price_bars;"
 14970    -- 499 bars x 30 symbols
$ psql ... -c "SELECT count(*) FROM indicators;"
171270   -- matches sum of each indicator's own warmup-adjusted count,
         -- e.g. SMA_20: 14400 = (499 - 19) days x 30 symbols, exactly
```

Idempotency check — re-running `compute_indicators_for_symbol` for AAPL over
the same date range reported **0 new rows** (correctly detected as already
computed, per ADR-012).

### Live endpoint verification

```
$ curl http://localhost:8000/api/v1/symbols
[... 30 symbols, e.g. {"id":1,"ticker":"AAPL","name":"Apple Inc.", ...}]

$ curl "http://localhost:8000/api/v1/symbols/AAPL/bars?start=2026-07-01&end=2026-08-03"
[... 22 real bars, e.g. {"as_of":"2026-07-31","open":"304.810000", ...,"close":"308.910000", ...}]

$ curl http://localhost:8000/api/v1/symbols/AAPL/indicators
[... 12 real indicator values for 2026-07-31, e.g. RSI_14=43.243931,
     MACD_HIST=-1.365218, BB_MID=324.367000 (exactly equal to SMA_20, as
     required by services/indicators.py's reuse-not-reimplement design)]
```

### Bug found and fixed during this phase

`compute_indicators_for_symbol()` initially used `CursorResult.rowcount` to
report how many indicator rows it inserted. During the live run this printed
`-1` for every symbol — a real, observed psycopg3 driver quirk for bulk
multi-row `INSERT ... ON CONFLICT DO NOTHING`, not a hypothetical concern.
Verified the underlying data was correct throughout (all counts above tie
out exactly) — only the reported count was wrong. Fixed by adding
`.returning(Indicator.id)` to the insert statement and counting the returned
rows, which is portable and correct regardless of driver-specific rowcount
behavior. Re-ran ingestion after the fix; report now correctly shows `5709`
(not `-1`) new rows per symbol, and `0` on the idempotency re-check.

### Secrets check before commit

Confirmed `apps/api/.env` (containing the real Alpaca keys) does not appear
in `git status --porcelain` output; `.gitignore`'s `.env` pattern still
covers it. Only `.env.example` changes (if any) would be staged.

## Phase 3 — Paper Portfolio & Trade Tracking (2026-08-03)

### Migration round-trip

```
$ uv run alembic upgrade head
INFO  Running upgrade bd027d9f35a2 -> 6fa6b9fd2ff4, create paper_portfolios, paper_orders, audit_events
```
The migration was regenerated once mid-phase (added a missing
`filled_quantity` column to `PaperOrder` — needed to correctly represent a
`PARTIALLY_FILLED` order, since `quantity` alone is the *requested* amount)
before it had been committed anywhere, so no fixup migration was needed —
just downgrade, delete, regenerate, re-apply. Round-trip verified clean
(same explicit-enum-drop fix from Phase 2 applied proactively this time).
`alembic check` confirms zero drift between the final models and the
migration.

### `apps/api` full suite

```
$ uv run ruff check . && uv run ruff format --check . && uv run mypy .
All checks passed! / 54 files already formatted / Success: no issues found in 53 source files

$ uv run pytest -v
============================= test session starts =============================
collected 40 items

tests/test_alpaca_market_data.py .....                                   [ ...]
tests/test_alpaca_paper_broker.py ......                                 [ ...]
tests/test_health.py .                                                   [ ...]
tests/test_indicators.py .............                                  [ ...]
tests/test_paper_orders_endpoints.py .............                       [ ...]
tests/test_symbols_endpoints.py ....                                    [100%]

======================== 40 passed, 1 warning in 1.86s =========================
```
17 new tests this phase: 6 for `AlpacaPaperBrokerProvider` (mocked
`TradingClient`, including the asynchronous-fill case), 13 for the order
flow (in-memory SQLite + a fake `PaperBrokerProvider` — insufficient
cash/position rejection, unknown symbol, propose→confirm happy path,
double-confirm rejection, same-cycle fill catch-up, `/refresh` catching a
later fill, refresh rejected on a terminal order, cancel, reconciliation
match/mismatch).

### Live verification (real Alpaca paper account)

Proposed and confirmed a real order:
```
$ curl -X POST localhost:8000/api/v1/paper-orders -d '{"ticker":"SPY","side":"BUY","quantity":1,"order_type":"MARKET"}'
{"id":1, ..., "status":"DRAFT", ...}

$ curl -X POST localhost:8000/api/v1/paper-orders/1/confirm
{"id":1, ..., "status":"SUBMITTED", "broker_order_id":"cc95fe9c-3c88-4355-bd4c-1ac16f7e51f6", ...}
```

**Bug caught here, live:** confirm's response showed `SUBMITTED`, not
`FILLED`. Querying Alpaca directly moments later showed the order had
actually filled:
```
$ python -c "... client.get_order_by_id('cc95fe9c-...')"
Market open: True as of 2026-08-03 10:55:15-04:00
Order status: OrderStatus.FILLED filled_qty: 1 filled_avg_price: 754.92
```
This is what motivated ADR-016 (`get_paper_order_status` +
`/refresh` endpoint). After implementing the fix and restarting the server:
```
$ curl -X POST localhost:8000/api/v1/paper-orders/1/refresh
{"id":1, "status":"FILLED", "filled_quantity":1, "filled_avg_price":"754.920000",
 "broker_order_id":"cc95fe9c-3c88-4355-bd4c-1ac16f7e51f6", ...}
```

Portfolio and reconciliation after the refresh:
```
$ curl localhost:8000/api/v1/portfolio
{
  "cash_usd": "9245.080000",
  "positions": [{"ticker":"SPY","quantity":1,"avg_entry_price":"754.920000",
                 "current_price":"747.030000","market_value":"747.030000","unrealized_pl":"-7.890000"}],
  "total_market_value": "747.030000", "total_equity": "9992.110000"
}
```
Cash check: `10000.00 - 754.92 = 9245.08` ✓ (exactly matches, confirming
`get_derived_cash()` is correct).

```
$ curl localhost:8000/api/v1/portfolio/reconciliation
[{"ticker":"SPY","our_quantity":1,"alpaca_quantity":"1","discrepancy":"0"}]
```
Zero discrepancy — our derived position exactly matches Alpaca's real
paper-account position report, the Phase 3 reconciliation deliverable,
verified against live data end-to-end.

### Secrets check before commit

No new secrets introduced this phase (same Alpaca keys as Phase 2, already
in the gitignored `apps/api/.env`). Confirmed `.env` still absent from
`git status --porcelain` before staging.

## Phase 4 — Scoring Engine & LLM Synthesis (2026-08-03)

### Migration round-trip

```
$ uv run alembic upgrade head
INFO  Running upgrade 6fa6b9fd2ff4 -> cd811cf4102b, create strategy_versions, recommendations, llm_call_logs

$ uv run alembic downgrade 6fa6b9fd2ff4
INFO  Running downgrade cd811cf4102b -> 6fa6b9fd2ff4, create strategy_versions, recommendations, llm_call_logs

$ uv run alembic upgrade head
INFO  Running upgrade 6fa6b9fd2ff4 -> cd811cf4102b, create strategy_versions, recommendations, llm_call_logs
```
Clean round-trip, including the FK from `paper_orders.linked_recommendation_id`
to `recommendations.id` and the two new native enum types
(`recommendation_confidence`, `recommendation_status`) — both explicitly
dropped in `downgrade()` (the ADR-011-era enum-drop fix, applied
proactively this time, not discovered the hard way again). `psql \dt`
confirmed all 10 tables exist after the final upgrade.

### `apps/api` full suite

```
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
73 files already formatted

$ uv run mypy .
Success: no issues found in 72 source files

$ uv run pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 71 items

tests/test_alpaca_market_data.py .....                                   [ ...]
tests/test_alpaca_paper_broker.py ......                                 [ ...]
tests/test_anthropic_llm.py ....                                         [ ...]
tests/test_ask.py ...                                                    [ ...]
tests/test_ask_endpoint.py ....                                          [ ...]
tests/test_health.py .                                                   [ ...]
tests/test_indicators.py .............                                  [ ...]
tests/test_llm_tools.py .............                                    [ ...]
tests/test_paper_orders_endpoints.py .............                       [ ...]
tests/test_scoring.py ......                                             [ ...]
tests/test_symbols_endpoints.py ....                                    [100%]

======================== 71 passed, 1 warning in 4.10s =========================
```
31 new tests this phase: 6 hand-computed scoring invariants (all-bullish
→100/HIGH, all-bearish→0/HIGH, 2v2 tie→50/LOW, 3v1→MEDIUM not HIGH, 3v1-
neutral→HIGH, no-data→50/LOW), 4 for `AnthropicLLMProvider` (mocked
`anthropic.Anthropic` client — text-only, tool-use, and multi-block
responses), 13 for `services/llm_tools.py`'s dispatcher (each tool's happy
path, unknown-ticker/invalid-enum error handling, unknown-tool and missing-
argument validation), 3 for `services/ask.py`'s orchestration loop (a
scripted 2-turn tool-call-then-answer flow with `LLMCallLog` rows verified,
an unknown-tool-name error handled without crashing, and the 5-iteration
cap), 4 for the `/api/v1/ask` and `/api/v1/paper-orders`-style dependency-
override endpoint tests (happy path, blank-question 422, rate-limit 429,
missing-API-key 503). All fixtures-only — no live Anthropic call required
to pass `pytest`.

### Live verification (real Anthropic API)

Real Anthropic API key provided by the user, dropped into the gitignored
`apps/api/.env`. Started the API against the real Postgres database (30
symbols, real price history/indicators from Phase 2's live ingestion) and
made a real `/api/v1/ask` call:

```
$ curl -X POST localhost:8000/api/v1/ask -H "Content-Type: application/json" \
    -d '{"question": "What does AAPL current setup look like, and what is your recommendation?"}'
{
  "answer": "**AAPL Setup — as of 2026-07-31** ... SMA_20: $324.37 | SMA_50: $309.50 ...
             RSI_14: 43.2 ... MACD line (6.89) below signal (8.26) ... Bollinger Bands:
             price near the lower band ($304.73) ... **Computed Recommendation
             (recommendation_id 1):** Score: 37.50 / 100, Confidence: LOW, Signal
             breakdown: trend +1, momentum 0, macd -1, bollinger -1 ...
             This is decision support only — not investment advice, and no order
             has been or will be placed.",
  "recommendations": [
    {"recommendation_id": 1, "symbol_ticker": "AAPL", "score": "37.50",
     "confidence": "LOW", "signal_breakdown": {"trend": 1, "momentum": 0, "macd": -1, "bollinger": -1}}
  ],
  "llm_call_log_ids": [1, 2],
  "iterations": 2
}
```

This is a genuine two-turn tool-use round trip: turn 1 the model called
`get_price_summary`, `get_indicators`, and `compute_recommendation` for
AAPL; turn 2 it synthesized the final answer from those tool results only
(the rationale text visibly matches the tool-returned numbers exactly —
SMA_20/SMA_50/RSI_14/MACD/Bollinger/score all trace back to real DB values,
not invented ones). The model also correctly stayed in its "not investment
advice, no order placed" lane per the system prompt guardrail, unprompted.

Real `LLMCallLog` rows, confirmed via `psql`:
```
$ psql -U tradingos_app -h localhost -d tradingos -c \
    "SELECT id, prompt_version, model, input_tokens, output_tokens, cost_usd FROM llm_call_logs ORDER BY id;"
 id | prompt_version |      model      | input_tokens | output_tokens | cost_usd
----+----------------+-----------------+--------------+---------------+----------
  1 | ask-v1         | claude-sonnet-5 |         1487 |           191 | 0.004884
  2 | ask-v1         | claude-sonnet-5 |         2163 |           575 | 0.010076
(2 rows)
```
Total cost for this one request: **$0.01496** — consistent with
`services/llm_cost.py`'s documented intro pricing ($2.00/$10.00 per million
input/output tokens).

Real `Recommendation` row, confirmed via `psql`:
```
$ psql -U tradingos_app -h localhost -d tradingos -c \
    "SELECT id, symbol_id, score, confidence, status FROM recommendations ORDER BY id;"
 id | symbol_id | score | confidence | status
----+-----------+-------+------------+--------
  1 |         1 | 37.50 | LOW        | ACTIVE
```

Also spot-checked at the live server: an empty `question` still returns
`422` (request-validation guardrail unaffected by the live-key path).

### Stale dev-server note

A `uvicorn` process left running from earlier in this session (before this
phase's code existed) was still bound to port 8000 and initially caused the
first live request to hit stale code (`404` on `/api/v1/ask`, confirmed via
`GET /openapi.json` missing the path). Killed that process and started a
fresh one from current code before the live call above — not a bug in the
Phase 4 code itself, just a leftover local process.

### Secrets check before commit

No new secrets introduced by code changes this phase beyond the Anthropic
API key already added to the gitignored `apps/api/.env` earlier in the
phase. Confirmed `.env` still absent from `git status --porcelain` before
staging.

## Phase 5 — Backtesting (2026-08-03)

### Migration round-trip

```
$ uv run alembic upgrade head
INFO  Running upgrade cd811cf4102b -> 130bfdd45919, create backtest_runs

$ uv run alembic downgrade cd811cf4102b
INFO  Running downgrade 130bfdd45919 -> cd811cf4102b, create backtest_runs

$ uv run alembic upgrade head
INFO  Running upgrade cd811cf4102b -> 130bfdd45919, create backtest_runs

$ uv run alembic check
No new upgrade operations detected.
```
Clean round-trip. No native enum types in this migration at all (unlike
every prior one) — `BacktestRun` runs synchronously and only ever persists
in a complete state, so there's no status column to model and no
enum-drop fixup needed in `downgrade()`.

### `apps/api` full suite

```
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
80 files already formatted

$ uv run mypy .
Success: no issues found in 79 source files

$ uv run pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 92 items

tests/test_alpaca_market_data.py .....                                   [ ...]
tests/test_alpaca_paper_broker.py ......                                 [ ...]
tests/test_anthropic_llm.py ....                                         [ ...]
tests/test_ask.py ...                                                    [ ...]
tests/test_ask_endpoint.py ....                                          [ ...]
tests/test_backtest_endpoint.py .........                                [ ...]
tests/test_backtest_simulation.py ............                          [ ...]
tests/test_health.py .                                                   [ ...]
tests/test_indicators.py .............                                  [ ...]
tests/test_llm_tools.py .............                                    [ ...]
tests/test_paper_orders_endpoints.py .............                       [ ...]
tests/test_scoring.py ......                                             [ ...]
tests/test_symbols_endpoints.py ....                                    [100%]

======================== 92 passed, 1 warning in 5.79s =========================
```
21 new tests this phase, all fixtures-only (no live API required to pass):

`tests/test_backtest_simulation.py` (12, pure core — no DB): next-open
fill timing (proving an entry decided on day T fills at day T+1's open,
not T's own close); a signal on the last loaded bar is dropped, not
executed; `max_holding_days` force-exit; end-of-window force-close with
`exit_reason="END_OF_BACKTEST"`; no-pyramiding (a second bullish signal
while holding never opens a second position); whole-share flooring +
cash-cap sizing (including the "budget buys less than one share" skip
case); a fully hand-verified scenario asserting exact `ending_equity`,
`total_return_pct`, `max_drawdown_pct`, `win_rate_pct`, `avg_win_pct`,
`avg_loss_pct` against manually computed Decimal values; the buy-and-hold
benchmark helper; an empty-calendar edge case. **The headline no-look-ahead
test** (`TestNoLookAhead`): the same shared history run once truncated at
a boundary day and once extended further with everything after the
boundary deliberately mutated to extreme values — every trade and
equity-curve point on or before the boundary asserted byte-identical
between the two runs, directly satisfying docs/TEST_STRATEGY.md's Phase 5
commitment.

`tests/test_backtest_endpoint.py` (9, in-memory SQLite): a hand-authored
6-trading-day `PriceBar`+`Indicator` fixture for two symbols produces a
persisted `BacktestRun` with the expected shape; **the survivorship-bias
test** seeds one symbol marked `active=False` today and confirms it still
appears in the backtest's trade log (ADR-025); an explicit
`strategy_version_id` override (an all-zero-weights `StrategyVersion`,
which forces `compute_score`'s neutral-50 branch) is honored and produces
zero trades, proving the override actually changes behavior; unknown
`strategy_version_id` and no-price-history-in-range both 400; a
not-tracked `benchmark_ticker` returns `null`, not an error; list/detail/
404 contract tests; the default date-range resolution (dates omitted)
finds the seeded fixture correctly.

### Live verification (real ~2-year ingested history)

Ran the API against the real Postgres database (30 symbols, real price
history/indicators from Phase 2's live ingestion) and made a real
`POST /api/v1/backtests` call with an empty body (all defaults — full
~2-year window, default entry/exit/sizing params, `SPY` benchmark):

```
$ time curl -X POST localhost:8000/api/v1/backtests -H "Content-Type: application/json" -d '{}'
real  0m4.529s

{
  "id": 1, "strategy_version_id": 1,
  "date_range_start": "2024-08-03", "date_range_end": "2026-08-03",
  "parameters": {"entry_score_threshold": "65", "exit_score_threshold": "40",
                 "max_holding_days": 10, "position_size_pct": "0.10",
                 "starting_cash": "10000.00", "benchmark_ticker": "SPY"},
  "results_summary": {
    "ending_equity": "11502.809000", "total_return_pct": "15.0280900",
    "max_drawdown_pct": "13.64907690932735224551263087",
    "win_rate_pct": "42.14876033057851239669421488", "num_trades": 847,
    "avg_win_pct": "4.686472162381834349631266353",
    "avg_loss_pct": "-2.988473588237427985474374059",
    "benchmark_return_pct": "44.38710425605937608720862809",
    "equity_curve": [/* 499 points, one per trading day */],
    "trades": [/* 847 trades */]
  }
}
```

**Wall-clock time: 4.5 seconds** for the full 30-symbol, ~2-year (499
trading day) universe — comfortably synchronous, no background job
warranted (ADR-006-style reasoning holds).

Sanity checks against the raw numbers (not just trusting the summary):
- `equity_curve` has exactly 499 points; its last point
  (`{"as_of": "2026-07-31", "equity": "11502.809000"}`) matches
  `ending_equity` exactly, confirming the force-close-at-end-of-window
  bookkeeping doesn't change total equity (ADR-022).
- Exit-reason breakdown across all 847 trades: 458 `SIGNAL_EXIT` + 377
  `MAX_HOLDING_DAYS` + 12 `END_OF_BACKTEST` = 847, matching `num_trades`
  exactly.
- All 30 seeded symbols appear in the trade log at least once — confirms
  the full universe participates (`active` is never filtered — ADR-025).
- Spot-checked one trade by hand: `BA` entered 2024-09-03 @ $167.03 x5,
  exited 2024-09-04 @ $160.28 (`SIGNAL_EXIT`) — recomputing
  `(160.28-167.03)*5 = -33.75` and `(160.28-167.03)/167.03*100 =
  -4.041190205352...%` both match the stored `pnl_usd`/`pnl_pct` exactly.
- `SPY` benchmark buy-and-hold return (44.39%) comfortably exceeds the
  strategy's total return (15.03%) over the same window — plausible for a
  strong-bull-market 2024–2026 window and a threshold-based swing strategy
  that spends much of its time in cash between signals; not tuned or
  cherry-picked, just the default parameters' first real run.

Confirmed via `psql`: one `backtest_runs` row (id 1, `strategy_version_id`
1, correct date range) and one matching `audit_events` row
(`record_type='BACKTEST_RUN_CREATED'`, `ref_id=1`, `snapshot` containing
the exact parameters echoed above) — the ADR-024 audit-trail decision
verified live, not just in a test fixture.

### Stale dev-server note

Same class of issue as Phase 4: a `uvicorn` process left running from
earlier in this session (predating this phase's router) was still bound
to port 8000 and initially caused `POST /api/v1/backtests` to 404
(confirmed via `GET /openapi.json` missing the path). Killed it and
started a fresh process from current code before the live call above.

### Secrets check before commit

No new secrets this phase — Phase 5 makes no Alpaca or Anthropic API
calls at all (pure computation over already-ingested Postgres data).
Confirmed `.env` still absent from `git status --porcelain` before
staging.

## Phase 6 — Learning / Strategy-Review Loop (2026-08-03)

### Migration round-trip

```
$ uv run alembic upgrade head
INFO  Running upgrade 130bfdd45919 -> eed7cb451bdc, add strategy_version status lifecycle

$ uv run alembic downgrade 130bfdd45919
INFO  Running downgrade eed7cb451bdc -> 130bfdd45919, add strategy_version status lifecycle

$ uv run alembic upgrade head
INFO  Running upgrade 130bfdd45919 -> eed7cb451bdc, add strategy_version status lifecycle

$ uv run alembic check
No new upgrade operations detected.
```
Not purely additive (ADR-027) — `is_active` was a live `NOT NULL` column
with a real row, so `upgrade()` adds `status` nullable, backfills
(`is_active=true → ACTIVE`, `is_active=false → PROPOSED`), sets `NOT
NULL`, then drops `is_active`. One real gotcha hit and fixed during this
migration's first attempt: `op.add_column()` on an *existing* table does
**not** implicitly `CREATE TYPE` for an `sa.Enum` column the way
`op.create_table()` does — the first run failed with
`psycopg.errors.UndefinedObject: type "strategy_version_status" does not
exist`. Fixed by explicitly calling `status_enum.create(op.get_bind(),
checkfirst=True)` before `op.add_column()`. Confirmed via `psql` after
the round-trip that the one real seeded row (`Plan of Record v1`)
correctly backfilled to `status = 'ACTIVE'`.

### `apps/api` full suite

```
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
85 files already formatted

$ uv run mypy .
Success: no issues found in 84 source files

$ uv run pytest -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
collected 107 items
...
======================= 107 passed, 1 warning in 3.77s ========================
```
15 new tests this phase, all fixtures-only (no live API required to
pass): `tests/test_strategy.py` (3, pure `compute_comparison_delta` —
candidate-better, candidate-worse, and identical-summaries cases, hand-
computed deltas, no DB). `tests/test_strategy_versions_endpoint.py` (12,
in-memory SQLite, a minimal price-only fixture since these tests are
about the state machine and audit trail, not backtest correctness
already covered in Phase 5): propose (happy path; invalid `rsi_bullish_low
>= rsi_bullish_high` → 422; doesn't touch any active version); compare
(persists exactly 2 new `BacktestRun` rows; candidate status unchanged;
404 on unknown id); approve (happy path — candidate becomes `ACTIVE`, the
lazily-created default becomes `SUPERSEDED`, one `STRATEGY_VERSION_APPROVED`
`AuditEvent` with both backtest ids and the previous-active id in its
snapshot; approving a second time → 400; 404 on unknown id); reject
(happy path — `REJECTED`, no `BacktestRun` rows created, active version
untouched, one `STRATEGY_VERSION_REJECTED` `AuditEvent`; rejecting twice →
400); list/detail.

### Live verification (real ingested history)

Started the API against the real Postgres database (the real
`Plan of Record v1` `StrategyVersion` already `ACTIVE` from prior phases)
and ran a real propose → compare → approve flow.

**Propose** a candidate with different weights (momentum up-weighted,
Bollinger down-weighted):
```
$ curl -X POST localhost:8000/api/v1/strategy-versions -d '{
    "name": "Momentum-weighted candidate",
    "config": {"weights": {"trend": 1.0, "momentum": 1.5, "macd": 1.0, "bollinger": 0.5},
               "rsi_bullish_low": 50, "rsi_bullish_high": 70, "rsi_oversold": 30}}'
{"id":2,"name":"Momentum-weighted candidate","status":"PROPOSED","decided_at":null, ...}
```

**Compare** it against the active version (real time: 6.4s for the pair
of backtests over the full ~2-year/30-symbol history):
```
$ curl -X POST localhost:8000/api/v1/strategy-versions/2/compare -d '{"benchmark_ticker": null}'
candidate (id 2) total_return_pct: 14.9277600
active    (id 1) total_return_pct: 15.0280900
delta: {"total_return_pct": "-0.1003300", "max_drawdown_pct": "5.447...",
        "win_rate_pct": "9.782...", "num_trades": -148, ...}
```
The candidate's momentum-weighted config traded 148 fewer times and
returned marginally less than the active version over this window —
exactly the kind of concrete, quantified trade-off the review gate exists
to surface (not to decide on).

**Approve** anyway, with a comment (real time: 5.4s — approve re-runs the
comparison itself per ADR-028, never trusting the `/compare` call above):
```
$ curl -X POST localhost:8000/api/v1/strategy-versions/2/approve -d '{
    "benchmark_ticker": null, "comment": "Live Phase 6 verification approval"}'
{"id":2,"status":"ACTIVE","decided_at":"2026-08-03T16:57:27...",
 "decision_comment":"Live Phase 6 verification approval", ...}
```

Confirmed final state via `psql`:
```
$ psql ... -c "SELECT id, name, status, decided_at, decision_comment FROM strategy_versions ORDER BY id;"
 id |            name             |   status   |          decided_at           |          decision_comment
----+-----------------------------+------------+-------------------------------+------------------------------------
  1 | Plan of Record v1           | SUPERSEDED |                                |
  2 | Momentum-weighted candidate | ACTIVE     | 2026-08-03 16:57:27.545043-07 | Live Phase 6 verification approval

$ psql ... -c "SELECT record_type, ref_id, snapshot FROM audit_events WHERE record_type LIKE 'STRATEGY_VERSION%' ORDER BY id;"
 STRATEGY_VERSION_PROPOSED | 2 | {"name": "Momentum-weighted candidate", "config": {...}}
 STRATEGY_VERSION_APPROVED | 2 | {"delta": {...}, "comment": "Live Phase 6 verification approval",
                                  "active_backtest_run_id": 7, "candidate_backtest_run_id": 6,
                                  "previous_active_strategy_version_id": 1}
```
The previous `ACTIVE` version correctly flipped to `SUPERSEDED`; the
candidate is now `ACTIVE` with `decided_at`/`decision_comment` set; both
`AuditEvent` rows exist with the exact data expected — `STRATEGY_VERSION_
PROPOSED` capturing the submitted config, `STRATEGY_VERSION_APPROVED`
referencing the exact two `BacktestRun` ids (6, 7) the approval was based
on and the previous active version's id (1), matching `run_comparison()`'s
real output exactly.

Note on `backtest_runs` row count: 7 total (1 pre-existing from Phase 5's
own live verification, plus 3 pairs from this session — the `/compare`
call's pair, an inadvertent duplicate `/compare` call triggered by a
verification-script fallback branch, and `/approve`'s own fresh pair).
Harmless — every pair is a real, correctly-attributed backtest — but
noted for an accurate record rather than silently reporting a cleaner
number than what actually happened.

### Secrets check before commit

No new secrets this phase — Phase 6 makes no Alpaca or Anthropic API
calls at all (pure computation over already-ingested Postgres data plus
the existing backtest engine). Confirmed `.env` still absent from
`git status --porcelain` before staging.

## Phase 7 — UI Polish & Documentation Hardening (2026-08-03)

### `apps/api` full suite — confirming zero backend drift

No backend code changed this phase (UI-only). Re-ran the full suite
anyway per the phase's acceptance criteria:

```
$ ruff check .
All checks passed!

$ ruff format --check .
85 files already formatted

$ mypy .
Success: no issues found in 84 source files

$ pytest -v
============================= test session starts =============================
collected 107 items
...
======================= 107 passed, 1 warning in 11.27s ========================
```
Identical 107/107 pass count to Phase 6's checkpoint — confirms no drift.

### `apps/web` component tests, lint, typecheck

```
$ pnpm lint
$ eslint
(no output = no errors)

$ pnpm typecheck
$ tsc --noEmit
(no output = no errors)

$ pnpm test
$ vitest run
 Test Files  5 passed (5)
      Tests  20 passed (20)
```

20 new tests this phase, across 4 new files (dashboard coverage already
existed from Phase 1, extended in this phase's rewrite of `page.tsx`):

- `__tests__/portfolio.test.tsx` (3): propose→DRAFT-row-appears; the
  `ConfirmButton` two-step gate (first click reveals "Are you sure?"
  without submitting, second click actually confirms and the row's
  status flips DRAFT→SUBMITTED); a propose error (400) surfaces via
  `ErrorBanner` without adding a row.
- `__tests__/strategy-versions.test.tsx` (4): the Review card (Compare/
  Approve/Reject) only renders while `PROPOSED`; `Compare against active`
  renders the delta and two `BacktestReport`s; the `ConfirmButton` gate
  on Reject, ending in a REJECTED status and the Review card disappearing;
  an approve error (400) surfaces via `ErrorBanner` with status unchanged.
- `__tests__/ask.test.tsx` (5): an empty `recommendations` array renders
  no recommendation chips; a populated array renders ticker/score/
  confidence-pill chips; the 429/503/422-specific `ErrorBanner` copy each
  render correctly for their respective status codes.
- `__tests__/backtest-report.test.tsx` (5): the summary metrics grid
  renders correctly formatted values (including a spot-check against the
  exact real numbers from Phase 5's live verification — `$11,502.81`,
  `15.03%`, `847` trades, `44.39%` benchmark return); one trade-log row
  per trade with a `StatusPill` for `exit_reason`; empty-state copy for
  zero trades and an empty equity curve; a null `benchmark_return_pct`
  renders `—` instead of crashing. `EquityCurveChart` is mocked in this
  file and in `strategy-versions.test.tsx` — jsdom has no real `<canvas>`
  2D context, so `lightweight-charts` can't actually mount in these tests
  (see the chart components' own comments); these tests cover data-shape
  and empty-state handling, not real chart rendering, per the approved
  Phase 7 plan's explicit priority-5 note for chart-adjacent components.

### Bug found and fixed while writing the strategy-versions test

Asserting on the rendered `+4.00%` delta text
(`__tests__/strategy-versions.test.tsx`) initially failed — a real
correctness bug in `components/strategy/CompareView.tsx`'s `DeltaMetric`:
it called `Number(value)` on a string its own caller had already suffixed
with `%` (e.g. `"4.00%"`), which is `NaN` in JavaScript, so the `+` prefix
and emerald/red tone silently never rendered correctly regardless of the
delta's actual sign — verified directly:
```
$ node -e "console.log(Number('4.00%'), Number('-1.00%'), Number('4.00'))"
NaN NaN 4
```
Fixed by stripping a trailing `%` before parsing
(`Number(value.replace(/%$/, ""))`). This had shipped silently in Phase
6's original `CompareView.tsx` and was never caught by manual curl-based
verification (which only inspects raw JSON, not rendered UI text/color) —
found only once a component test asserted on the actual rendered string
(ADR-031's discussion of this bug has the full before/after).

### `apps/web` e2e (Playwright, ADR-030)

Both servers already running locally (`uvicorn` on :8000 via the venv
directly, `pnpm dev` on :3000). Installed Chromium
(`pnpm exec playwright install chromium`) and ran the one e2e test:

```
$ pnpm exec playwright test
Running 1 test using 1 worker

  ok 1 [chromium] › e2e\paper-order-flow.spec.ts:10:5 › propose and confirm a paper order for a seeded liquid symbol (1.8s)

  1 passed (2.4s)
```

This is a real, unmocked run against the real Alpaca paper-trading API —
proposes a `MARKET BUY 1 AAPL` order, confirms it through the
`ConfirmButton` gate, and asserts the row's status leaves `DRAFT` for
`SUBMITTED`/`FILLED`.

One config fix needed along the way: `e2e/paper-order-flow.spec.ts`'s
`test(...)` calls were initially also being picked up by `vitest run`
(both frameworks default to `*.spec.ts` discovery), causing a spurious
Vitest failure with no relation to any application bug. Fixed by adding
`exclude: ["**/node_modules/**", "**/e2e/**"]` to `vitest.config.mts`.

### Live click-through of the full demo path (Browser tool)

Both dev servers running against the real Postgres database (all prior
phases' seeded/live-verified data intact). Walked the exact path named in
the approved Phase 7 plan's verification section.

**Environment limitation, disclosed up front:** this session's Browser
pane reported "the Browser pane is not displayed, so the page is not
compositing frames," which broke `computer{action:"screenshot"}` outright
and — less obviously — also broke coordinate/`ref`-based clicks on real
interactive elements (a click on "Propose order" produced no network
request at all) and canvas pixel-buffer inspection (`canvas.width`/
`.height` stuck at the browser's uninitialized 300×150 default across all
chart canvases, and `canvas.toDataURL()` producing byte-identical output
for all of them, consistent with Chromium suspending/throttling
`requestAnimationFrame` — which `lightweight-charts` uses for its actual
draw calls — for a non-composited tab). Worked around every case with an
approach that doesn't depend on visual compositing: `javascript_tool`-
dispatched `element.click()` calls (verified via `read_network_requests`
that these produce real POST/GET calls, unlike the coordinate clicks),
`get_page_text`/`read_page` for content verification, and
`read_console_messages` for error-checking. This is a tooling/environment
artifact of this specific session, not an application defect — confirmed
by finding `lightweight-charts`' own "Charting by TradingView"
attribution link present in the accessibility tree (proving the chart
library itself initialized correctly even though its canvas never drew a
visible frame), and by every JS-dispatched click producing the correct
real network call and real state change described below.

**Dashboard → Symbols → symbol chart:** loaded `/`, confirmed the
portfolio snapshot and API-status card render with real data. Navigated
to a symbol detail page; confirmed the latest-indicators text readout
matches real DB values already verified in Phase 2's evidence (SMA_20
$324.37, SMA_50 $309.50, RSI_14 43.24, etc.).

**Portfolio — propose/confirm a real paper order:** filled the order
form, JS-dispatched-clicked "Propose order" — a `DRAFT` row appeared.
JS-dispatched-clicked "Confirm" (revealing "Are you sure?"), then
"Confirm" again — `read_network_requests` confirmed a real
`POST /api/v1/paper-orders/{id}/confirm` returning `200`, and the row's
status updated to `SUBMITTED` in the UI without a manual refresh
(TanStack Query invalidation working as designed).

**Backtests, Strategy Versions — propose/compare/reject:** proposed a
fresh "Phase 7 UI test candidate" `StrategyVersion` via the real form.
On its detail page, clicked "Compare against active" (JS-dispatched,
waited ~8s for two real backtests) — `CompareView` rendered with real
delta metrics and both `BacktestReport`s; the Candidate side showed
`$11,502.81` ending equity / `15.03%` return / `847` trades / `44.39%`
benchmark return, exactly matching Phase 5's live-verified numbers (the
active `Plan of Record`-lineage version's backtest is deterministic given
the same underlying price history — see ADR-022). Clicked "Reject"
(revealing the `ConfirmButton` gate), then "Confirm rejection" — the
page's final text confirmed:
```
Phase 7 UI test candidate
REJECTED
Config
{ "weights": {...}, "rsi_oversold": "30", ... }
```
and the Review card (Compare/Approve/Reject) correctly disappeared once
the version left `PROPOSED`, matching `isProposed` gating in
`app/strategy-versions/[id]/page.tsx`.

**Ask — real Anthropic call:** navigated to `/ask`, filled "What does
AAPL's current setup look like?" (a TradingOS-appropriate question — a
generic placeholder question from an unrelated exercise was typed in by
mistake first and corrected before submitting), JS-dispatched-clicked
"Send". `read_network_requests` confirmed a real
`POST /api/v1/ask` → `200`. The rendered answer:

```
Here's AAPL's current technical picture as of 2026-07-31:
Latest close: $308.91 ... SMA_20: $324.37 | SMA_50: $309.50 ...
RSI_14: 43.24 ... MACD histogram is negative (-1.37) ...
Bollinger Bands: ... price is in the lower half of the band ...
I haven't run the deterministic scoring model yet — want me to call
compute_recommendation for AAPL ...? Remember, this is decision support
only — final call is yours.
```
Every number matches the real DB values from Phase 2's ingestion exactly,
confirming the model is grounded in real tool results, not inventing
figures (principles 6/7) — and it correctly stayed in its
decision-support-only lane unprompted, same as Phase 4's live
verification. `read_console_messages` showed zero errors throughout.

This completes live verification of every page and both review flows
through the real UI (not just curl, as in Phases 3/6) — the full demo
path named in PROJECT_INSTRUCTIONS.md's working method.

### Secrets check before commit

No new secrets this phase — `apps/web` never references the Anthropic
key or any Alpaca credential anywhere (docs/SECURITY.md's Phase 7 review
note). Confirmed `.env`/`.env.local` still absent from
`git status --porcelain` before staging.
