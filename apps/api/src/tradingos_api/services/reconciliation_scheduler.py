"""The reconciliation scheduler (Revision Prompt 16 idempotency review
— "scheduled reconciliation"). Decides, given "now" and when an
account last reconciled, whether an automatic reconciliation should
fire — the actual work is `services/reconciliation.py::reconcile_from_broker()`'s
job; this module only answers "should a run start right now."

**Local mode vs. an always-on worker** — the same distinction
`morning_plan_scheduler.py::decide_schedule()` documents applies here
verbatim: this function is a pure decision, not a timer. Nothing in
this deployment currently calls it on an interval (task: real
always-on scheduler/worker process); until that exists, automatic
reconciliation only happens when something — a person, a script —
calls `POST /api/v1/portfolio/accounts/{id}/reconcile-automatic`
manually or `decide_reconciliation_schedule()` itself directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.portfolio_ext import ReconciliationRun

DEFAULT_RECONCILIATION_CADENCE = timedelta(hours=24)


@dataclass(frozen=True)
class ReconciliationScheduleDecision:
    should_run: bool
    reason: str


def decide_reconciliation_schedule(
    db: Session,
    *,
    account_id: uuid.UUID,
    now: datetime,
    cadence: timedelta = DEFAULT_RECONCILIATION_CADENCE,
) -> ReconciliationScheduleDecision:
    """`should_run=True` iff no reconciliation run exists for this
    account yet, or the most recent one's `as_of` is older than
    `cadence`. Always returns a `reason`, whether or not a run should
    fire — "already reconciled recently" is as observable a decision as
    "time to run," matching this project's existing scheduler
    convention (never a bare boolean)."""
    latest = db.scalar(
        select(ReconciliationRun)
        .where(ReconciliationRun.account_id == account_id)
        .order_by(ReconciliationRun.as_of.desc())
    )
    if latest is None:
        return ReconciliationScheduleDecision(
            should_run=True, reason="no prior reconciliation run exists for this account"
        )

    age = now - latest.as_of
    if age >= cadence:
        return ReconciliationScheduleDecision(
            should_run=True,
            reason=f"last run was {age} ago, at or past the {cadence} cadence",
        )
    return ReconciliationScheduleDecision(
        should_run=False,
        reason=f"last run was only {age} ago, under the {cadence} cadence",
    )


__all__ = [
    "DEFAULT_RECONCILIATION_CADENCE",
    "ReconciliationScheduleDecision",
    "decide_reconciliation_schedule",
]
