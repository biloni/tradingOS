"""Revision Prompt 16, task: real always-on scheduler/worker process —
the per-tick job glue between a pure decision and an actual run.

`services/morning_plan_scheduler.py::decide_schedule()` and
`services/reconciliation_scheduler.py::decide_reconciliation_schedule()`
only ever answered "is this due right now" — nothing called them on a
timer, and neither one runs generation/reconciliation itself. This
module is what a real timer (`core/scheduler.py`) calls each tick: for
one user's morning plan, or one account's reconciliation, decide
whether it's due and, if so, actually run it and commit — the same
underlying generation/reconciliation logic a manual "run now" call
already uses (`routers/morning_plan.py::generate_plan()`,
`routers/portfolio.py::reconcile_account_automatic()`), just triggered
by the clock instead of a person clicking a button.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AlertDeliveryStatus as AlertDeliveryStatusEnum,
)
from tradingos_api.models.enums import (
    AlertSeverity,
    AlertType,
    DeliveryChannel,
    MorningPlanRunStatus,
    MorningPlanVersionLabel,
)
from tradingos_api.models.execution import Account
from tradingos_api.models.morning_plan import MorningPlanDeliveryEvent, MorningPlanVersion
from tradingos_api.models.operations import Alert
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.services.morning_plan_generate import generate_morning_plan
from tradingos_api.services.morning_plan_scheduler import (
    ScheduleDecision,
    decide_schedule,
    record_run_outcome,
    record_run_start,
)
from tradingos_api.services.reconciliation import reconcile_from_broker
from tradingos_api.services.reconciliation_scheduler import (
    ReconciliationScheduleDecision,
    decide_reconciliation_schedule,
)

_logger = logging.getLogger("tradingos_api.scheduler")

# Matches this project's one `triggered_by` vocabulary for `MorningPlanRun`
# (a free-text field — "manual", "AD_HOC", etc. elsewhere) so a run's
# provenance is visible at a glance in the job dashboard (routers/ops.py).
SCHEDULER_TRIGGERED_BY = "scheduler"


def run_due_morning_plan_for_user(
    db: Session, *, user_id: uuid.UUID, now: datetime
) -> ScheduleDecision:
    """One user's morning-plan tick. Mirrors
    `routers/morning_plan.py::generate_plan()`'s body for the schedule
    case specifically (`version_label`/`idempotency_key` come from
    `decide_schedule()` itself, not a request payload) — same
    record_run_start()/record_run_outcome() bookkeeping, same FINAL-only
    Alert/MorningPlanDeliveryEvent. Returns the decision either way so
    the caller can log/observe a no-op tick without treating it as an
    error."""
    decision = decide_schedule(db, now_utc=now)
    if not decision.should_run:
        return decision

    account = db.scalar(select(Account).where(Account.owner_user_id == user_id))
    if account is None:
        _logger.warning(
            "scheduler skipped due morning plan: user has no account",
            extra={"user_id": str(user_id)},
        )
        return decision

    assert decision.version_label is not None
    assert decision.idempotency_key is not None

    prior_max = db.scalar(
        select(MorningPlanVersion.version_number)
        .where(MorningPlanVersion.plan_date == decision.plan_date)
        .order_by(MorningPlanVersion.version_number.desc())
    )
    next_version_number = (prior_max or 0) + 1

    run = record_run_start(
        db,
        plan_date=decision.plan_date,
        triggered_by=SCHEDULER_TRIGGERED_BY,
        idempotency_key=decision.idempotency_key,
        started_at=now,
    )

    try:
        result = generate_morning_plan(
            db,
            run=run,
            plan_date=decision.plan_date,
            version_label=decision.version_label,
            version_number=next_version_number,
            now=now,
            account_id=account.id,
        )
    except Exception as exc:
        record_run_outcome(run, status=MorningPlanRunStatus.FAILED, completed_at=datetime.now(UTC))
        run.error_detail = str(exc)
        db.commit()
        _logger.exception(
            "scheduled morning plan generation failed",
            extra={"user_id": str(user_id), "run_id": str(run.id)},
        )
        return decision

    if result.skipped:
        record_run_outcome(
            run, status=MorningPlanRunStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        db.commit()
        return decision

    record_run_outcome(run, status=MorningPlanRunStatus.COMPLETED, completed_at=datetime.now(UTC))
    assert result.version is not None

    # "In-app notification when the final plan is ready" — only for
    # FINAL, matching generate_plan()'s own rule.
    if decision.version_label == MorningPlanVersionLabel.FINAL:
        db.add(
            Alert(
                owner_user_id=user_id,
                instrument_id=None,
                alert_type=AlertType.SYSTEM_NOTIFICATION,
                severity=AlertSeverity.INFO,
                title=f"Morning plan ready — {decision.plan_date.isoformat()}",
                detail=(
                    f"The FINAL morning decision plan for {decision.plan_date.isoformat()} has "
                    f"been published (completeness: {result.version.completeness_status.value})."
                ),
                triggered_at=datetime.now(UTC),
            )
        )
        db.add(
            MorningPlanDeliveryEvent(
                morning_plan_version_id=result.version.id,
                channel=DeliveryChannel.IN_APP,
                status=AlertDeliveryStatusEnum.DELIVERED,
                delivered_at=datetime.now(UTC),
            )
        )

    db.commit()
    _logger.info(
        "scheduled morning plan generated",
        extra={
            "user_id": str(user_id),
            "run_id": str(run.id),
            "version_label": decision.version_label.value,
        },
    )
    return decision


def run_due_reconciliation_for_account(
    db: Session, *, account: Account, broker: PaperBrokerProvider, now: datetime
) -> ReconciliationScheduleDecision:
    """One `PAPER_ALPACA` account's reconciliation tick. Mirrors
    `routers/portfolio.py::reconcile_account_automatic()`'s body — same
    `reconcile_from_broker()` call, same commit. Non-`PAPER_ALPACA`
    accounts have no broker feed to compare against (see that
    endpoint's own 422), so the caller is expected to only pass
    `PAPER_ALPACA` accounts here; this function does not re-check."""
    decision = decide_reconciliation_schedule(db, account_id=account.id, now=now)
    if not decision.should_run:
        return decision

    run, _replayed = reconcile_from_broker(
        db,
        account_id=account.id,
        broker=broker,
        as_of=now,
    )
    db.commit()
    _logger.info(
        "scheduled reconciliation completed",
        extra={
            "account_id": str(account.id),
            "run_id": str(run.id),
            "overall_status": run.overall_status.value,
        },
    )
    return decision


__all__ = [
    "SCHEDULER_TRIGGERED_BY",
    "run_due_morning_plan_for_user",
    "run_due_reconciliation_for_account",
]
