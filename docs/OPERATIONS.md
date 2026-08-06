# Operations

## Local development (the only supported environment as of Phase 1)

See README.md for the full quickstart. Summary:

1. PostgreSQL 16 running (native install on this dev machine — ADR-008 — or
   `docker compose -f infra/docker-compose.yml up -d` on another machine).
2. `apps/api`: `uv sync`, then `uv run uvicorn tradingos_api.main:app --reload`.
3. `apps/web`: `pnpm install`, then `pnpm dev`.

## Production deployment

**Not yet decided.** No hosting target, CI pipeline, or deployment process
exists as of Phase 1 — this is a personal local-dev project at this stage.
When a deployment phase is scoped, this section will cover: hosting choice,
environment variable management in that host, database backup/restore,
and how the Alpaca paper-account credentials and Anthropic key are provisioned
there without ever appearing in a repo or CI log.

## Monitoring / alerting

Not applicable yet — no deployed instance to monitor. Will be scoped
alongside the deployment decision above.

## Runbooks

None yet (nothing is running in a way that needs one). The one operational
procedure worth recording now, since it came up during Phase 1 setup:

### Resetting a lost local Postgres superuser password (Windows, native install)

1. Open `C:\Program Files\PostgreSQL\<version>\data\pg_hba.conf` in an
   elevated text editor; temporarily change the `local`/`host 127.0.0.1`/
   `host ::1` lines' auth method from `scram-sha-256` to `trust`.
2. Restart the `postgresql-x64-<version>` Windows service (elevated
   PowerShell: `Restart-Service postgresql-x64-<version>`).
3. Connect with "SQL Shell (psql)" (no password prompt in `trust` mode) and
   run `ALTER USER postgres WITH PASSWORD '<new password>';` — note the
   single quotes and terminating semicolon; without them psql will treat
   the statement as incomplete and swallow subsequent input as more SQL.
4. Revert `pg_hba.conf` back to `scram-sha-256` and restart the service
   again.

## v2 Decision and Execution Amendment (2026-08-05) — operating mode and kill switch

PROJECT_INSTRUCTIONS.md's new "TradingOS v2 Decision and Execution
Amendment" section (`OA-*`) requires four visibly distinct order-authority
modes and an always-available kill switch / cancel-open-orders control.
Neither is wired into a running deployment yet:

- **Local dev has no operating-mode setting today.** There is no
  `OPERATING_MODE` environment variable or config value anywhere in
  `apps/api` — every existing order endpoint behaves like an ungated
  `PAPER_MANUAL_APPROVAL` (see docs/SECURITY.md's v2 amendment note for
  the exact gap). When a future phase wires
  `apps/api/src/tradingos_api/policy/order_authority.py::assert_order_authorized()`
  into `routers/orders.py`, this section gets a real "which mode is this
  deployment running in, and how do I change it" runbook entry — not
  before, since there is no toggle to document yet.
- **Kill switch / cancel-open-orders — not built.** No live broker
  integration exists (principle 10, unchanged), so there is currently
  nothing for a kill switch to stop. The requirement is recorded here so
  it is scoped into the same phase that ever adds `PAPER_AUTO_POLICY` or
  `LIVE_CONFIRM_EACH_ORDER` order submission, rather than treated as an
  afterthought once orders are already flowing.
