"""The morning-plan scheduler (Revision Prompt 9). Decides, given "now"
and what has already run, whether a `PRELIMINARY` or `FINAL` generation
should fire — the actual generation work is
`services/morning_plan_generate.py`'s job; this module only answers
"should a run start right now, and for which trading date/version."

**Local mode vs. an always-on worker.** This function is deliberately
just a pure decision — it does not itself run on a timer. In production,
an always-on deployed worker (a process that never stops, e.g. a
scheduled cloud job or a long-running service) calls
`decide_schedule()` on a tight interval (e.g. every minute) and acts on
`should_run=True`. Run **locally** instead (a laptop, not a deployed
worker) and the schedule only fires while that laptop is awake and the
polling process is running — `LOCAL_MODE_WARNING` is the literal,
user-facing text this project shows wherever local-mode scheduling is
configured, so a user is never left assuming "it'll run itself" when it
requires their own machine to be on at 5:45am.

**Idempotent, retryable, observable, resumable, versioned:**
- *Idempotent*: `build_idempotency_key()` is unique per (trading date,
  version label, attempt) — `MorningPlanRun.idempotency_key`'s existing
  DB-level uniqueness (R3) is the actual enforcement mechanism.
- *Retryable*: a `FAILED` or stuck `RUNNING` (past `STUCK_RUN_TIMEOUT`)
  prior attempt for the same (date, label) does not block a new attempt
  — `decide_schedule()` computes the next attempt number itself.
- *Observable*: every decision returns a `reason` string, whether or not
  it results in a run — "already completed," "not yet time," "not a
  trading day," etc., never a bare boolean.
- *Resumable*: because each attempt is its own `MorningPlanRun` row
  (never mutated in place), a worker that crashed mid-run and restarted
  sees the same decision logic produce "retry attempt N" rather than
  silently losing track of an in-flight run (the required "worker
  restart" test).
- *Versioned*: the resulting `MorningPlanVersion.version_number` (R3)
  is a strictly increasing per-`plan_date` sequence regardless of how
  many attempts or corrections produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import MorningPlanRunStatus, MorningPlanVersionLabel
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.services.market_calendar import DISPLAY_TIMEZONE, resolve_trading_day

CALCULATION_VERSION = "v1"

DEFAULT_PRELIMINARY_TIME = time(5, 45)
DEFAULT_FINAL_TIME = time(6, 10)

# A run stuck in RUNNING past this long is treated as failed/abandoned
# (e.g. the worker process died mid-run) — eligible for a fresh retry
# attempt rather than blocking the slot forever.
STUCK_RUN_TIMEOUT = timedelta(minutes=15)

LOCAL_MODE_WARNING = (
    "Local scheduling mode: this schedule only fires while this computer is "
    "awake and the TradingOS process is running. If this machine sleeps, "
    "shuts down, or the process is not running at 5:45am/6:10am local time, "
    "no plan will be generated for that trading day. Deploy an always-on "
    "worker for unattended scheduling."
)


def build_idempotency_key(
    plan_date: date, version_label: MorningPlanVersionLabel, attempt: int = 1
) -> str:
    suffix = "" if attempt == 1 else f":attempt{attempt}"
    return f"morning-plan:{plan_date.isoformat()}:{version_label.value}{suffix}"


@dataclass(frozen=True)
class ScheduleDecision:
    should_run: bool
    plan_date: date
    version_label: MorningPlanVersionLabel | None
    attempt: int
    idempotency_key: str | None
    reason: str


def _runs_for_key_prefix(
    db: Session, plan_date: date, version_label: MorningPlanVersionLabel
) -> list[MorningPlanRun]:
    prefix = f"morning-plan:{plan_date.isoformat()}:{version_label.value}"
    all_runs = db.scalars(select(MorningPlanRun).where(MorningPlanRun.plan_date == plan_date)).all()
    return [
        r
        for r in all_runs
        if r.idempotency_key is not None
        and (r.idempotency_key == prefix or r.idempotency_key.startswith(f"{prefix}:attempt"))
    ]


def _decide_for_version(
    db: Session, *, plan_date: date, version_label: MorningPlanVersionLabel, now_utc: datetime
) -> ScheduleDecision:
    prior_runs = _runs_for_key_prefix(db, plan_date, version_label)

    if any(r.status == MorningPlanRunStatus.COMPLETED for r in prior_runs):
        return ScheduleDecision(
            should_run=False,
            plan_date=plan_date,
            version_label=version_label,
            attempt=len(prior_runs),
            idempotency_key=None,
            reason=f"{version_label.value} already completed for {plan_date.isoformat()}.",
        )

    stuck_or_failed = [
        r
        for r in prior_runs
        if r.status == MorningPlanRunStatus.FAILED
        or (r.status == MorningPlanRunStatus.RUNNING and now_utc - r.started_at > STUCK_RUN_TIMEOUT)
    ]
    still_running = [
        r
        for r in prior_runs
        if r.status == MorningPlanRunStatus.RUNNING and now_utc - r.started_at <= STUCK_RUN_TIMEOUT
    ]
    if still_running:
        return ScheduleDecision(
            should_run=False,
            plan_date=plan_date,
            version_label=version_label,
            attempt=len(prior_runs),
            idempotency_key=None,
            reason=f"{version_label.value} run already in progress for {plan_date.isoformat()}.",
        )

    attempt = len(prior_runs) + 1
    reason = (
        f"retrying {version_label.value} for {plan_date.isoformat()} (attempt {attempt}, "
        f"{len(stuck_or_failed)} prior failed/stuck attempt(s))"
        if prior_runs
        else f"starting {version_label.value} for {plan_date.isoformat()} (attempt 1)"
    )
    return ScheduleDecision(
        should_run=True,
        plan_date=plan_date,
        version_label=version_label,
        attempt=attempt,
        idempotency_key=build_idempotency_key(plan_date, version_label, attempt),
        reason=reason,
    )


def decide_schedule(
    db: Session,
    *,
    now_utc: datetime,
    preliminary_time: time = DEFAULT_PRELIMINARY_TIME,
    final_time: time = DEFAULT_FINAL_TIME,
) -> ScheduleDecision:
    """The one function an always-on worker's polling loop calls on
    every tick. Pure with respect to "now" (`now_utc` is a parameter,
    never `datetime.now()` read internally) so a controllable clock can
    drive it deterministically in tests and the demo."""
    now_local = now_utc.astimezone(DISPLAY_TIMEZONE)
    plan_date = now_local.date()

    trading_day = resolve_trading_day(plan_date)
    if not trading_day.is_trading_day:
        return ScheduleDecision(
            should_run=False,
            plan_date=plan_date,
            version_label=None,
            attempt=0,
            idempotency_key=None,
            reason=trading_day.skip_reason or "not a trading day",
        )

    local_time = now_local.time()
    if local_time >= final_time:
        return _decide_for_version(
            db, plan_date=plan_date, version_label=MorningPlanVersionLabel.FINAL, now_utc=now_utc
        )
    if local_time >= preliminary_time:
        return _decide_for_version(
            db,
            plan_date=plan_date,
            version_label=MorningPlanVersionLabel.PRELIMINARY,
            now_utc=now_utc,
        )
    return ScheduleDecision(
        should_run=False,
        plan_date=plan_date,
        version_label=None,
        attempt=0,
        idempotency_key=None,
        reason=(
            f"before today's preliminary run time ({preliminary_time.isoformat()} "
            f"{DISPLAY_TIMEZONE.key})."
        ),
    )


def record_run_start(
    db: Session, *, plan_date: date, triggered_by: str, idempotency_key: str, started_at: datetime
) -> MorningPlanRun:
    run = MorningPlanRun(
        plan_date=plan_date,
        triggered_by=triggered_by,
        status=MorningPlanRunStatus.RUNNING,
        idempotency_key=idempotency_key,
        started_at=started_at,
    )
    db.add(run)
    db.flush()
    return run


def record_run_outcome(
    run: MorningPlanRun, *, status: MorningPlanRunStatus, completed_at: datetime
) -> None:
    run.status = status
    run.completed_at = completed_at
