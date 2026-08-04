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
