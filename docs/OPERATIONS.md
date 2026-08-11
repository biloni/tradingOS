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

### Health and readiness (Revision Prompt 16)

Two endpoints, both reachable without authentication (an orchestrator
polling them has no session cookie):

- **`GET /health`** — pure liveness. Always `{"status": "ok", ...}` if
  the process can respond at all; deliberately checks nothing else, so
  a degraded dependency never causes an orchestrator to restart a
  perfectly healthy process.
- **`GET /ready`** — real dependency status
  (`routers/health.py::get_readiness`). Returns HTTP 200 with
  `"ready": true` only when the database is reachable (the one *hard*
  dependency — nothing in this app works without it); returns 503 with
  `"ready": false` otherwise. The response body's `checks` object
  always reports every dependency honestly:
  - `database` — `ok` / `error` (a real `SELECT 1`, not a ping to a
    cached connection pool state)
  - `market_data_provider` / `broker_provider` — `configured` /
    `not_configured` (same underlying Alpaca-credential check as
    `GET /api/v1/settings/providers`'s `has_credential_configured`) —
    absence never blocks readiness (principle 5: this app degrades to
    synthetic providers gracefully)
  - `llm_provider` — `configured` / `not_configured` (Anthropic key) —
    same non-blocking treatment
  - `scheduler` / `worker` — always `not_implemented` today. Neither a
    real timer-driven scheduler nor a background worker process exists
    in this deployment yet (see "Running the Morning Decision Plan
    schedule" below and task: real always-on scheduler/worker
    process) — `/ready` says so rather than reporting a fake "ok" for
    a process that doesn't exist.

No job dashboard or metrics scraping endpoint exists yet (separate,
already-tracked task).

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

### Running the Morning Decision Plan schedule (Revision Prompt 9)

`services/morning_plan_scheduler.py::decide_schedule()` is a pure
decision function — it does not run on a timer by itself. Something
external has to call it repeatedly and act on `should_run=True` by
calling `POST /api/v1/morning-plan/generate`. As of this revision, no
such polling process is deployed; this is the runbook for both modes.

**Local mode (this project's current state).** There is no background
worker process yet. To generate a plan locally:

- **Manual, right now:** `POST /api/v1/morning-plan/generate` directly
  with `"version_label": "AD_HOC"` (or omit it — that's the default).
  Rejects with 422 and a reason if today (or the given `plan_date`) is
  not a trading day.
- **Scheduled, while this machine is on:** run a small loop (not yet
  shipped as a script) that calls `decide_schedule(db, now_utc=...)`
  every minute or so and `POST`s `/generate` with the returned
  `version_label`/`idempotency_key` whenever `should_run=True`. This
  only fires while that loop's process is actually running.
- **`services/morning_plan_scheduler.py::LOCAL_MODE_WARNING` is the
  literal, user-facing text this project shows wherever local-mode
  scheduling is configured** — restated here verbatim so this runbook
  and the code never drift apart: *"Local scheduling mode: this
  schedule only fires while this computer is awake and the TradingOS
  process is running. If this machine sleeps, shuts down, or the
  process is not running at 5:45am/6:10am local time, no plan will be
  generated for that trading day. Deploy an always-on worker for
  unattended scheduling."*

**Deployed mode (not yet built).** A real deployment needs one
always-on worker process — a scheduled cloud job or a long-running
service, not this laptop — polling `decide_schedule()` and calling
`/generate` the same way. Nothing about the scheduler or orchestrator
contract changes between local and deployed mode; only *what calls
them, and how reliably it stays running* differs. Scoping and standing
up that worker is not yet done (tracked the same way the "Production
deployment" section above tracks the rest of the hosting decision).

**Demonstrating the whole flow without any of this wired up yet:**
`python -m tradingos_api.scripts.demo_prompt9` drives
`decide_schedule()` with a controllable clock across a synthetic
trading day — including a simulated worker crash mid-`FINAL`-run and a
successful retry after `STUCK_RUN_TIMEOUT` — calling the real
`/generate`/`/dashboard`/`/versions/{id}/export.md`/`/cowork-brief`
endpoints throughout. Its full transcript is in
docs/TEST_EVIDENCE.md's Revision Prompt 9 section.

**Troubleshooting a run that never produced a `FINAL` plan:**

1. `GET /api/v1/morning-plan/dashboard` — check `top_status.plan_status`.
   `MARKET_CLOSED` means today wasn't a trading day (check
   `market_closed_reason`); `INCOMPLETE` with no `plan_version_id` means
   nothing has run yet today; `FAILED` means the most recent attempt for
   today errored.
2. Query `morning_plan_runs` for today's `plan_date`, ordered by
   `started_at desc`. A `RUNNING` row older than 15 minutes
   (`STUCK_RUN_TIMEOUT`) is a crashed attempt — the next scheduler tick
   retries it automatically; nothing to do manually.
3. A `FAILED` row's `error_detail` column names the exception — the
   next scheduler tick (or a manual `POST /generate`) retries with an
   incremented idempotency-key attempt number automatically; no manual
   cleanup of the failed row is needed or wanted (it stays as the audit
   trail of that attempt).

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
