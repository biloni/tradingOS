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
