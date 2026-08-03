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
