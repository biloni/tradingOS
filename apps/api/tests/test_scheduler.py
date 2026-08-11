"""Tests for the always-on scheduler (Revision Prompt 16, task: real
always-on scheduler/worker process) — `services/scheduler_jobs.py`'s
per-subject job glue and `core/scheduler.py`'s APScheduler wrapper.

`core/scheduler.py::tick()` itself is deliberately never called
directly here: it opens its own `SessionLocal()` against the real dev
Postgres database with the real wall clock, outside
`tests/conftest.py`'s savepoint/rollback isolation (see that module's
own docstring) — calling it in a test would be a genuine, time-of-day-
dependent write to the shared dev database. Instead, the job functions
`tick()` calls are tested directly against the transactional
`db_session` fixture with a controlled `now`, and the scheduler
lifecycle (`start_scheduler()`/`stop_scheduler()`) is tested without
ever letting its 60-second interval actually fire.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.scheduler import get_scheduler_status, start_scheduler, stop_scheduler
from tradingos_api.models.enums import MorningPlanRunStatus, ReconciliationStatus
from tradingos_api.models.execution import Account
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.models.portfolio_ext import ReconciliationRun
from tradingos_api.services.scheduler_jobs import (
    SCHEDULER_TRIGGERED_BY,
    run_due_morning_plan_for_user,
    run_due_reconciliation_for_account,
)

# 2026-08-11 is a plain Tuesday (a real trading day) in America/Los_Angeles,
# the same fixed date `test_morning_plan_scheduler.py` uses.
_TRADING_DATE = "2026-08-11"


def _at(hour: int, minute: int) -> datetime:
    # Naive local wall-clock time in America/Los_Angeles for the fixed
    # trading date, expressed directly in UTC (PDT = UTC-7 in August).
    return datetime(2026, 8, 11, hour + 7, minute, tzinfo=UTC)


class _FakePositionsBroker:
    """Implements only what `reconcile_from_broker()` calls (mirrors
    `_FakePositionsBroker` in test_reconciliation_scheduler.py)."""

    def get_paper_positions(self) -> list[dict[str, str]]:
        return []


class TestRunDueMorningPlanForUser:
    def test_generates_a_run_when_due(self, db_session: Session, fresh_account: Account) -> None:
        decision = run_due_morning_plan_for_user(
            db_session, user_id=fresh_account.owner_user_id, now=_at(6, 15)
        )
        assert decision.should_run is True

        run = db_session.scalar(
            select(MorningPlanRun).where(MorningPlanRun.idempotency_key == decision.idempotency_key)
        )
        assert run is not None
        assert run.triggered_by == SCHEDULER_TRIGGERED_BY
        assert run.status == MorningPlanRunStatus.COMPLETED

    def test_no_run_created_before_the_scheduled_window(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        decision = run_due_morning_plan_for_user(
            db_session, user_id=fresh_account.owner_user_id, now=_at(5, 0)
        )
        assert decision.should_run is False

        runs = db_session.scalars(
            select(MorningPlanRun).where(MorningPlanRun.triggered_by == SCHEDULER_TRIGGERED_BY)
        ).all()
        assert len(runs) == 0

    def test_second_tick_in_the_same_window_does_not_duplicate(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        first = run_due_morning_plan_for_user(
            db_session, user_id=fresh_account.owner_user_id, now=_at(6, 15)
        )
        second = run_due_morning_plan_for_user(
            db_session, user_id=fresh_account.owner_user_id, now=_at(6, 16)
        )
        assert first.should_run is True
        assert second.should_run is False
        assert "already completed" in second.reason


class TestRunDueReconciliationForAccount:
    def test_creates_a_run_when_due(self, db_session: Session) -> None:
        account = db_session.scalar(select(Account).limit(1))
        assert account is not None
        broker = _FakePositionsBroker()
        now = datetime.now(UTC)

        decision = run_due_reconciliation_for_account(
            db_session,
            account=account,
            broker=broker,
            now=now,  # type: ignore[arg-type]
        )
        assert decision.should_run is True

        run = db_session.scalar(
            select(ReconciliationRun)
            .where(ReconciliationRun.account_id == account.id)
            .order_by(ReconciliationRun.created_at.desc())
        )
        assert run is not None
        assert run.overall_status == ReconciliationStatus.MATCHED

    def test_no_run_when_recently_reconciled(self, db_session: Session) -> None:
        account = db_session.scalar(select(Account).limit(1))
        assert account is not None
        now = datetime.now(UTC)
        db_session.add(
            ReconciliationRun(
                account_id=account.id,
                as_of=now - timedelta(hours=1),
                overall_status=ReconciliationStatus.MATCHED,
            )
        )
        db_session.flush()

        broker = _FakePositionsBroker()
        decision = run_due_reconciliation_for_account(
            db_session,
            account=account,
            broker=broker,
            now=now,  # type: ignore[arg-type]
        )
        assert decision.should_run is False
        assert "under the" in decision.reason


class TestSchedulerLifecycle:
    def test_start_then_stop_toggles_running_status(self) -> None:
        try:
            start_scheduler()
            assert get_scheduler_status().running is True

            # Idempotent — a second start while already running must not
            # raise or spawn a second job.
            start_scheduler()
            assert get_scheduler_status().running is True
        finally:
            stop_scheduler()

        assert get_scheduler_status().running is False

    def test_status_reports_the_configured_tick_interval(self) -> None:
        status = get_scheduler_status()
        assert status.tick_interval_seconds == 60
