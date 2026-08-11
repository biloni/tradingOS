"""Revision Prompt 16, task: real always-on scheduler/worker process.

`docs/BLOCKING_DECISIONS.md` #4's recorded choice: an in-process
scheduler (APScheduler) running inside this same FastAPI process,
triggering the same service-layer functions the API routes call — no
Redis, no Celery, no separate deployable. `main.py`'s `lifespan`
context manager starts it on app startup and stops it on shutdown
(`start_scheduler()`/`stop_scheduler()` below).

Every tick opens its own `SessionLocal()` — it isn't a request, so
there's no `Depends(get_db)` to participate in. This deliberately means
a background tick is invisible to `tests/conftest.py`'s savepoint/
rollback machinery (see that file's docstring); the only thing that
makes tests safe is that `TestClient(app)` is never entered as a
context manager in this project's `client` fixture, so lifespan startup
never fires under pytest, and this module's own tests call `tick()`
directly against a `db_session`-backed session instead of starting a
real timer.

**Still local-mode, not "deployed."** This satisfies "an always-on
process exists and polls the decision functions" — it does not change
the fact that the process has to actually be running (a laptop asleep
or a process not started still means nothing fires). `morning_plan_scheduler.LOCAL_MODE_WARNING`
is unchanged and still accurate; a real deployment (task: Dockerfiles +
deployment docs) is what makes "always-on" actually true, not this
module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from tradingos_api.core.dependencies import get_broker_provider
from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import AccountType
from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.services.scheduler_jobs import (
    run_due_morning_plan_for_user,
    run_due_reconciliation_for_account,
)

_logger = logging.getLogger("tradingos_api.scheduler")

TICK_INTERVAL_SECONDS = 60
_JOB_ID = "tradingos-scheduler-tick"

_scheduler: BackgroundScheduler | None = None
_last_tick_at: datetime | None = None
_last_tick_error: str | None = None
_tick_count = 0


@dataclass(frozen=True)
class SchedulerStatus:
    running: bool
    tick_interval_seconds: int
    tick_count: int
    last_tick_at: datetime | None
    last_tick_error: str | None


def tick() -> None:
    """One pass over every user's morning plan and every `PAPER_ALPACA`
    account's reconciliation. Each job runs in its own try/except so
    one user's or one account's failure never blocks the rest of the
    tick — matches this project's existing "log and continue" pattern
    for anything that scans multiple independent subjects."""
    global _last_tick_at, _last_tick_error, _tick_count
    now = datetime.now(UTC)
    db = SessionLocal()
    error_messages: list[str] = []
    try:
        user_ids = db.scalars(select(UserProfile.id)).all()
        for user_id in user_ids:
            try:
                run_due_morning_plan_for_user(db, user_id=user_id, now=now)
            except Exception as exc:  # noqa: BLE001 - one user's failure must not stop the tick
                db.rollback()
                error_messages.append(f"morning plan ({user_id}): {exc}")
                _logger.exception(
                    "scheduler tick: morning plan job raised", extra={"user_id": str(user_id)}
                )

        broker = get_broker_provider()
        accounts = db.scalars(
            select(Account).where(Account.account_type == AccountType.PAPER_ALPACA)
        ).all()
        for account in accounts:
            try:
                run_due_reconciliation_for_account(db, account=account, broker=broker, now=now)
            except Exception as exc:  # noqa: BLE001 - one account's failure must not stop the tick
                db.rollback()
                error_messages.append(f"reconciliation ({account.id}): {exc}")
                _logger.exception(
                    "scheduler tick: reconciliation job raised",
                    extra={"account_id": str(account.id)},
                )
    finally:
        db.close()

    _last_tick_at = now
    _last_tick_error = "; ".join(error_messages) if error_messages else None
    _tick_count += 1


def start_scheduler() -> None:
    """Idempotent — calling this twice (e.g. a hot-reload) replaces
    rather than doubles up the scheduled job, since APScheduler dedupes
    by `id=_JOB_ID`."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    scheduler = BackgroundScheduler(timezone=UTC)
    scheduler.add_job(tick, "interval", seconds=TICK_INTERVAL_SECONDS, id=_JOB_ID)
    scheduler.start()
    _scheduler = scheduler
    _logger.info("scheduler started", extra={"tick_interval_seconds": TICK_INTERVAL_SECONDS})


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        _logger.info("scheduler stopped")


def get_scheduler_status() -> SchedulerStatus:
    return SchedulerStatus(
        running=_scheduler is not None and _scheduler.running,
        tick_interval_seconds=TICK_INTERVAL_SECONDS,
        tick_count=_tick_count,
        last_tick_at=_last_tick_at,
        last_tick_error=_last_tick_error,
    )


__all__ = [
    "SchedulerStatus",
    "get_scheduler_status",
    "start_scheduler",
    "stop_scheduler",
    "tick",
]
