"""Scheduler decision tests (Revision Prompt 9) — the required
"duplicate/rerun protection" and "worker restart" categories, plus the
weekend/holiday routing `decide_schedule()` itself owns on top of
`resolve_trading_day()`.

`decide_schedule()` is a pure function of `now_utc` and whatever
`MorningPlanRun` rows already exist — no wall clock is read internally —
so every scenario here is driven by a literal, controllable timestamp
rather than freezing real time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from tradingos_api.models.enums import MorningPlanRunStatus, MorningPlanVersionLabel
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.services.morning_plan_scheduler import (
    STUCK_RUN_TIMEOUT,
    build_idempotency_key,
    decide_schedule,
    record_run_outcome,
    record_run_start,
)

# 2026-08-11 is a plain Tuesday (a real trading day) in America/Los_Angeles.
_TRADING_DATE = "2026-08-11"


def _at(hour: int, minute: int) -> datetime:
    # Naive local wall-clock time in America/Los_Angeles for the fixed
    # trading date, expressed directly in UTC (PDT = UTC-7 in August).
    return datetime(2026, 8, 11, hour + 7, minute, tzinfo=UTC)


class TestBeforePreliminaryWindow:
    def test_no_run_before_545am_local(self, db_session: Session) -> None:
        decision = decide_schedule(db_session, now_utc=_at(5, 0))
        assert decision.should_run is False
        assert decision.version_label is None
        assert "before" in decision.reason.lower()


class TestWeekendAndHoliday:
    def test_weekend_never_schedules_a_run_regardless_of_time_of_day(
        self, db_session: Session
    ) -> None:
        saturday_morning = datetime(2026, 8, 8, 13, 0, tzinfo=UTC)  # ~06:00 PT Saturday
        decision = decide_schedule(db_session, now_utc=saturday_morning)
        assert decision.should_run is False
        assert decision.version_label is None
        assert "weekend" in decision.reason.lower()

    def test_holiday_never_schedules_a_run(self, db_session: Session) -> None:
        labor_day_morning = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)  # Labor Day, ~06:00 PT
        decision = decide_schedule(db_session, now_utc=labor_day_morning)
        assert decision.should_run is False
        assert "holiday" in decision.reason.lower()


class TestPreliminaryThenFinalWindows:
    def test_between_545_and_610_schedules_preliminary(self, db_session: Session) -> None:
        decision = decide_schedule(db_session, now_utc=_at(5, 50))
        assert decision.should_run is True
        assert decision.version_label == MorningPlanVersionLabel.PRELIMINARY
        assert decision.attempt == 1
        assert decision.idempotency_key == build_idempotency_key(
            datetime(2026, 8, 11).date(), MorningPlanVersionLabel.PRELIMINARY, 1
        )

    def test_at_or_after_610_schedules_final(self, db_session: Session) -> None:
        decision = decide_schedule(db_session, now_utc=_at(6, 10))
        assert decision.should_run is True
        assert decision.version_label == MorningPlanVersionLabel.FINAL


class TestDuplicateRerunProtection:
    def test_a_completed_preliminary_run_blocks_a_second_preliminary_attempt(
        self, db_session: Session
    ) -> None:
        first = decide_schedule(db_session, now_utc=_at(5, 50))
        assert first.should_run is True
        assert first.idempotency_key is not None
        run = record_run_start(
            db_session,
            plan_date=first.plan_date,
            triggered_by="worker",
            idempotency_key=first.idempotency_key,
            started_at=_at(5, 50),
        )
        record_run_outcome(run, status=MorningPlanRunStatus.COMPLETED, completed_at=_at(5, 51))
        db_session.flush()

        second = decide_schedule(db_session, now_utc=_at(6, 0))
        assert second.should_run is False
        assert second.version_label == MorningPlanVersionLabel.PRELIMINARY
        assert "already completed" in second.reason.lower()

    def test_a_still_running_attempt_blocks_a_concurrent_second_attempt(
        self, db_session: Session
    ) -> None:
        first = decide_schedule(db_session, now_utc=_at(5, 50))
        assert first.idempotency_key is not None
        record_run_start(
            db_session,
            plan_date=first.plan_date,
            triggered_by="worker",
            idempotency_key=first.idempotency_key,
            started_at=_at(5, 50),
        )
        db_session.flush()

        # A second poll tick, moments later, while the first run is
        # still in flight (no outcome recorded yet) — must not schedule
        # a duplicate concurrent run for the same slot.
        second = decide_schedule(db_session, now_utc=_at(5, 51))
        assert second.should_run is False
        assert "already in progress" in second.reason.lower()

    def test_idempotency_key_is_stable_for_the_same_date_label_and_attempt(self) -> None:
        key_a = build_idempotency_key(
            datetime(2026, 8, 11).date(), MorningPlanVersionLabel.PRELIMINARY, 1
        )
        key_b = build_idempotency_key(
            datetime(2026, 8, 11).date(), MorningPlanVersionLabel.PRELIMINARY, 1
        )
        assert key_a == key_b == "morning-plan:2026-08-11:PRELIMINARY"


class TestWorkerRestart:
    def test_a_failed_attempt_allows_a_fresh_retry_with_an_incremented_attempt_number(
        self, db_session: Session
    ) -> None:
        first = decide_schedule(db_session, now_utc=_at(5, 50))
        assert first.idempotency_key is not None
        run = record_run_start(
            db_session,
            plan_date=first.plan_date,
            triggered_by="worker",
            idempotency_key=first.idempotency_key,
            started_at=_at(5, 50),
        )
        record_run_outcome(run, status=MorningPlanRunStatus.FAILED, completed_at=_at(5, 51))
        db_session.flush()

        retry = decide_schedule(db_session, now_utc=_at(5, 55))
        assert retry.should_run is True
        assert retry.attempt == 2
        assert retry.idempotency_key == build_idempotency_key(
            first.plan_date, MorningPlanVersionLabel.PRELIMINARY, 2
        )
        assert "retrying" in retry.reason.lower()

    def test_a_run_stuck_in_running_past_the_timeout_is_treated_as_abandoned_and_retried(
        self, db_session: Session
    ) -> None:
        # Simulates a worker process that crashed mid-run: the
        # `MorningPlanRun` row is left `RUNNING` forever with no
        # completion — a restarted worker polling later must not be
        # blocked by it indefinitely.
        stuck_start = _at(5, 50)
        run = MorningPlanRun(
            plan_date=datetime(2026, 8, 11).date(),
            triggered_by="worker",
            status=MorningPlanRunStatus.RUNNING,
            idempotency_key=build_idempotency_key(
                datetime(2026, 8, 11).date(), MorningPlanVersionLabel.PRELIMINARY, 1
            ),
            started_at=stuck_start,
        )
        db_session.add(run)
        db_session.flush()

        still_within_timeout = decide_schedule(
            db_session, now_utc=stuck_start + STUCK_RUN_TIMEOUT - timedelta(minutes=1)
        )
        assert still_within_timeout.should_run is False
        assert "already in progress" in still_within_timeout.reason.lower()

        past_timeout = decide_schedule(
            db_session, now_utc=stuck_start + STUCK_RUN_TIMEOUT + timedelta(minutes=1)
        )
        assert past_timeout.should_run is True
        assert past_timeout.attempt == 2
        assert "retrying" in past_timeout.reason.lower()

    def test_restart_after_a_completed_final_still_correctly_blocks_further_runs(
        self, db_session: Session
    ) -> None:
        # A worker that restarts after having already published FINAL
        # for the day must not re-run it just because it lost in-memory
        # state — the decision is derived entirely from persisted rows.
        first = decide_schedule(db_session, now_utc=_at(6, 15))
        assert first.version_label == MorningPlanVersionLabel.FINAL
        assert first.idempotency_key is not None
        run = record_run_start(
            db_session,
            plan_date=first.plan_date,
            triggered_by="worker",
            idempotency_key=first.idempotency_key,
            started_at=_at(6, 15),
        )
        record_run_outcome(run, status=MorningPlanRunStatus.COMPLETED, completed_at=_at(6, 16))
        db_session.flush()

        after_restart = decide_schedule(db_session, now_utc=_at(6, 20))
        assert after_restart.should_run is False
        assert "already completed" in after_restart.reason.lower()
