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
  - `scheduler` / `worker` — `ok` when `core/scheduler.py`'s in-process
    APScheduler is running (this process's lifespan started it and
    `SCHEDULER_ENABLED` isn't `false`), `not_running` otherwise — never
    faked as healthy just because the API process itself is up. See
    "Real always-on scheduler/worker process" below.

### Job dashboard + metrics (Revision Prompt 16)

- **`GET /api/v1/ops/metrics`** — in-process, stdlib-only request
  metrics (`core/metrics.py`): uptime, total requests, status-class
  counts (2xx/4xx/5xx/...), and latency (avg/p50/p95 over the most
  recent 2000 requests). Resets on process restart and reflects only
  this one server process — no aggregation pipeline exists (no
  Prometheus, no external scraper); this is a same-process, in-memory
  summary only, exposed as JSON.
- **`GET /api/v1/ops/job-runs`** — the job dashboard's content:
  `MorningPlanRun` rows, most recent first, capped at 100. This is the
  one recurring "job" concept this app actually has today (see
  "Running the Morning Decision Plan schedule" above) — `JobRun`,
  `CommitteeSession`, `AgentRun`, and `ReconciliationRun` all track
  runs too, but weren't pulled into this first pass; scope this wider
  if a future revision needs it.
- **Frontend**: `/ops` page (`apps/web/app/ops/page.tsx`) renders both,
  polling every 15s.
- Both endpoints require authentication (unlike `/health`/`/ready`) —
  this is operational data about the app's own internals, not
  something an infra orchestrator with no credentials needs.

### Cost-budget-triggered kill switch (Revision Prompt 16)

- **`Settings.daily_llm_cost_budget_usd`** (default `$5.00`) — no fixed
  figure is specified anywhere in this project's docs
  (`docs/PROVIDER_MATRIX.md` gives *monthly* planning estimates, Normal
  ~$8-17, Heavy ~$45-100); $5/day (~$150/month) is a deliberately
  generous daily backstop chosen to catch a genuine runaway loop, not
  to nag on ordinary heavy usage. Override via env for a tighter
  personal limit.
- **Enforcement** (`services/cost_budget.py::check_and_enforce_cost_budget`)
  runs inline, once per committee run
  (`services/committee_orchestrator.py::run_committee()`) — a
  synchronous check at the one place LLM cost actually accrues,
  unchanged by the in-process scheduler below (that worker doesn't run
  committee sessions, so it has no cost to check). Sums
  `ModelCallRecord.cost_usd` since UTC midnight; if
  that meets or exceeds the budget and the kill switch isn't already
  active, activates it with `activated_by="system:cost-budget"` and a
  reason naming the exact spend/budget figures. Never re-activates or
  overwrites an already-active switch (including a human's own
  activation) — a no-op if one is already tripped.
- The triggering run itself still completes and persists normally — a
  trip only prevents the *next* committee run (which checks
  `is_kill_switch_active()` before anything else) and any order-
  authority action, matching the kill switch's existing "stop what's
  next, don't corrupt what's in-flight" behavior elsewhere.
- **`GET /api/v1/ops/cost-budget`** — read-only status (today's spend,
  the configured budget, remaining headroom, whether the kill switch
  is active). Rendered on the `/ops` page. Deactivating a
  budget-tripped kill switch uses the same existing
  `POST /api/v1/settings/kill-switch/deactivate` endpoint (step-up
  required) as any other kill-switch deactivation — no separate
  "clear the budget trip" action exists or is needed.

### Idempotency gaps + scheduled reconciliation (Revision Prompt 16)

A review found `confirm`/`cancel`/`cancel-open`/`reconcile` all had a
real gap the pre-existing state-machine checks alone didn't cover —
none of it was "silently corrupts data on a normal retry," but each had
a real, closable weakness:

- **`POST /orders/{id}/confirm` and `.../cancel`** — the existing
  `assert_transition_allowed()` check already 400s a *sequential*
  replay cleanly. The real gap was concurrent: two simultaneous
  requests could both read the same pre-transition status and both
  pass the check before either committed. Fixed with
  `db.get(Order, order_id, with_for_update=True)` — a `SELECT ... FOR
  UPDATE` row lock, so a second concurrent request blocks until the
  first transaction commits, then correctly sees the updated status.
- **`POST /orders/cancel-open`** — `services/order_execution.py::cancel_order_at_broker()`
  had no status guard at all, and could call
  `broker.cancel_paper_order()` on an already-canceled order (raising
  on the synthetic provider). Now idempotent: returns the order
  unchanged if it isn't `SUBMITTED`/`PARTIALLY_FILLED`. The router's
  own order-selection query also gained `with_for_update()`, closing
  the same concurrent-race window as confirm/cancel.
- **`POST /portfolio/accounts/{id}/reconcile`** — the one confirmed
  clean gap: no idempotency key, no dedup, every call (replay or not)
  created a new `ReconciliationRun`/`ReconciliationLine` set. Fixed
  with an optional client-supplied `idempotency_key` (matching this
  project's established convention, `docs/API_CONTRACTS.md`) — a
  repeated key returns the original run (`replayed: true` in the
  response) instead of a duplicate.
- **`POST /portfolio/accounts/{id}/reconcile-automatic`** (new) —
  reconciliation was "only manually triggered" in a second sense too:
  the only path required a human to type broker-reported quantities
  into the request body. This endpoint calls
  `PaperBrokerProvider.get_paper_positions()` directly instead (only
  meaningful for a `PAPER_ALPACA` account — `MANUAL` accounts have no
  broker feed, same 422 as the existing manual-entry endpoint).
- **`services/reconciliation_scheduler.py::decide_reconciliation_schedule()`**
  — the same pure-decision-function pattern
  `morning_plan_scheduler.py::decide_schedule()` already established:
  "should this account reconcile now" based on time since its last run
  (default cadence 24h). Not on a timer yet — nothing in this
  deployment calls it on an interval (task: real always-on
  scheduler/worker process, below); it exists so that worker has
  something ready to call the moment it exists, rather than inventing
  scheduling logic from scratch then.

### Real always-on scheduler/worker process (Revision Prompt 16)

`docs/BLOCKING_DECISIONS.md` #4's recorded choice, now built:
`core/scheduler.py` runs an in-process APScheduler (`BackgroundScheduler`)
inside this same FastAPI process — no Redis, no Celery, no separate
deployable. `main.py`'s `lifespan` context manager starts it on app
startup and stops it on shutdown; `Settings.scheduler_enabled` (default
`True`, env var `SCHEDULER_ENABLED`) can turn it off entirely.

- **What it does, every 60 seconds** (`core/scheduler.py::tick()`):
  for every `UserProfile`, calls
  `services/scheduler_jobs.py::run_due_morning_plan_for_user()`
  (`decide_schedule()` + the same generation/notification logic
  `POST /morning-plan/generate` uses, `triggered_by="scheduler"`); for
  every `PAPER_ALPACA` account, calls
  `run_due_reconciliation_for_account()` (`decide_reconciliation_schedule()`
  + `reconcile_from_broker()`). Each subject's job runs in its own
  try/except — one user's or one account's failure is logged and
  rolled back, never blocks the rest of the tick.
- **Status**: `GET /api/v1/ops/scheduler` (also rendered on `/ops`) and
  `/ready`'s `scheduler`/`worker` checks both read
  `core/scheduler.py::get_scheduler_status()` — `running`,
  `tick_interval_seconds`, `tick_count`, `last_tick_at`,
  `last_tick_error`.
- **Still local mode, not "deployed."** This satisfies "an always-on
  process exists and polls the decision functions" for as long as this
  process is running — it does not change the fact that a laptop
  asleep, or the process not started, still means nothing fires.
  `morning_plan_scheduler.LOCAL_MODE_WARNING` is unchanged and still
  accurate. A real deployment (task: Dockerfiles + deployment docs) —
  not this module — is what makes "always-on" actually true.
- **Why tests never start it**: FastAPI's `TestClient` only runs
  lifespan startup/shutdown when entered as a context manager
  (`with TestClient(app) as c:`); `tests/conftest.py::client` never
  does that, so the scheduler stays `not_running` under the whole test
  suite, and its per-subject job functions are tested directly against
  the transactional `db_session` fixture instead of the real
  `tick()`/`SessionLocal()` (`tests/test_scheduler.py`'s own docstring
  explains why `tick()` itself is never called in a test).

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
decision function — it does not run on a timer by itself.
`core/scheduler.py`'s in-process APScheduler (see "Real always-on
scheduler/worker process" above) is what calls it every 60 seconds and
acts on `should_run=True` today; this is the runbook for both that
process and manual/ad-hoc generation.

**Local mode (this project's current state).** An in-process worker
exists (`core/scheduler.py`) and runs whenever the API process is
running, but it's still *local*: it only fires while this laptop is
awake and the process hasn't been stopped.

- **Manual, right now:** `POST /api/v1/morning-plan/generate` directly
  with `"version_label": "AD_HOC"` (or omit it — that's the default).
  Rejects with 422 and a reason if today (or the given `plan_date`) is
  not a trading day.
- **Scheduled, while this machine is on:** happens automatically —
  `core/scheduler.py::tick()` calls `decide_schedule()` every 60
  seconds for every user and runs generation itself
  (`services/scheduler_jobs.py::run_due_morning_plan_for_user()`,
  `triggered_by="scheduler"`) whenever `should_run=True`. No separate
  script or manual polling loop is needed anymore. Set
  `SCHEDULER_ENABLED=false` to disable it (e.g. running the API for a
  one-off script that shouldn't race the real scheduler).
- **`services/morning_plan_scheduler.py::LOCAL_MODE_WARNING` is the
  literal, user-facing text this project shows wherever local-mode
  scheduling is configured** — restated here verbatim so this runbook
  and the code never drift apart: *"Local scheduling mode: this
  schedule only fires while this computer is awake and the TradingOS
  process is running. If this machine sleeps, shuts down, or the
  process is not running at 5:45am/6:10am local time, no plan will be
  generated for that trading day. Deploy an always-on worker for
  unattended scheduling."* That warning is still accurate even with
  `core/scheduler.py` running — "in-process" is not "always-on";
  "always-on" needs a real deployment.

**Deployed mode (not yet built).** A real deployment needs this same
process — or an equivalent one — actually staying up on a host that
doesn't sleep, not this laptop. Nothing about the scheduler or
orchestrator contract changes between local and deployed mode; only
*how reliably the process stays running* differs. Standing up that
deployment is not yet done (tracked the same way the "Production
deployment" section above tracks the rest of the hosting decision;
task: Dockerfiles + deployment docs).

**Demonstrating the whole flow without the in-process worker involved:**
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
