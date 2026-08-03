# Status

**Current phase:** Phase 1 — Foundations & Architecture
**Last updated:** 2026-08-03

## Done

- Repo scaffolded: `apps/web` (Next.js 16 + TS + Tailwind + TanStack Query +
  lightweight-charts), `apps/api` (FastAPI + SQLAlchemy 2.0 + Alembic,
  uv-managed), `infra/docker-compose.yml`.
- Vendor/scope decisions confirmed with the user and recorded as ADRs
  (docs/DECISIONS.md): Alpaca Markets, US equities+ETFs only,
  `lightweight-charts`, `uv`/`ruff`/`mypy` + `pnpm`/ESLint/`tsc`, Redis and
  Playwright deferred, no auth in MVP.
- Local PostgreSQL 16 running natively on this dev machine; dedicated
  least-privilege `tradingos_app` role and `tradingos` database created.
- `/health` endpoint live in the API; the web app's home page renders an
  API-reachability status card powered by it.
- Lint, format, type-check, and unit tests all passing on both apps
  (see docs/TEST_EVIDENCE.md for exact commands/output once the full
  verification pass runs).
- All 15 required repository documents + docs/DEPENDENCIES.md written.
- Full end-to-end verification workflow run: native Postgres reachable,
  API and web check suites all passing, both dev servers verified live in
  the browser with the web page successfully calling the API and zero
  console errors. See docs/TEST_EVIDENCE.md.

## In progress / next

- Create the Phase 1 checkpoint commit.
- **Then stop and wait** — Phase 2 (data ingestion) does not start until
  explicitly requested, per the working method.

## Known blockers

None currently open. (One transient local-environment issue was resolved
during this phase: the winget-installed Postgres had no recoverable
superuser password; the user reset it via the standard PostgreSQL
trust-mode recovery procedure — see ADR-008.)

## Deferred (not blockers, intentional)

- Docker-based local dev (compose file exists, documented, but native
  Postgres is the primary path on this machine — ADR-008).
- Playwright e2e tests (no real user journey exists yet to test — ADR-006).
- Redis (no demonstrated need yet — ADR-006).
