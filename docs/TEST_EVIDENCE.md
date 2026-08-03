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
