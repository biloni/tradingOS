"""Cost-budget-triggered kill switch (Revision Prompt 16: "cost budgets
and kill switches"). Checked inline, once per committee run
(`services/committee_orchestrator.py::run_committee()`) — this app has
no background worker process yet (task: real always-on
scheduler/worker), so a synchronous check at the one place LLM cost
actually accrues is the only enforcement point that runs today. A
future worker process could instead poll this on a timer; the check
itself doesn't change either way.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.models.operations import ModelCallRecord
from tradingos_api.services.order_authority import activate_kill_switch, is_kill_switch_active

SYSTEM_ACTIVATED_BY = "system:cost-budget"


def get_todays_llm_spend_usd(db: Session, *, now: datetime | None = None) -> Decimal:
    """Sums `ModelCallRecord.cost_usd` created since UTC midnight — the
    simplest, unambiguous cadence. A "trading day" definition would
    need market-calendar awareness this check has no reason to carry;
    LLM cost accrues on wall-clock time, not trading sessions."""
    now = now or datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(ModelCallRecord.cost_usd), 0)).where(
            ModelCallRecord.created_at >= day_start
        )
    )
    return Decimal(total) if total is not None else Decimal(0)


def check_and_enforce_cost_budget(db: Session, *, now: datetime | None = None) -> bool:
    """Returns True if this call just tripped the kill switch. A no-op
    (returns False, does not re-activate or touch the existing event)
    if the kill switch is already active — never clobbers a
    human-entered activation with this function's own reason, and
    never double-activates. Does not commit — same contract as
    `activate_kill_switch()` itself; the caller controls the
    transaction."""
    now = now or datetime.now(UTC)
    if is_kill_switch_active(db):
        return False

    budget = get_settings().daily_llm_cost_budget_usd
    spend = get_todays_llm_spend_usd(db, now=now)
    if spend < budget:
        return False

    activate_kill_switch(
        db,
        activated_by=SYSTEM_ACTIVATED_BY,
        reason=(
            f"Daily LLM cost budget exceeded: ${spend} spent >= ${budget} budget "
            f"(UTC {now.date().isoformat()})"
        ),
        now=now,
    )
    return True


__all__ = ["SYSTEM_ACTIVATED_BY", "check_and_enforce_cost_budget", "get_todays_llm_spend_usd"]
