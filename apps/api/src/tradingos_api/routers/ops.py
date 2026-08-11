"""Job dashboard + metrics (Revision Prompt 16). Gated by
`require_session` like every other business router (`main.py`) —
unlike `/health`/`/ready`, this is operational data about the app's
own internals, not something an infra orchestrator with no credentials
needs to poll.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.core.metrics import request_metrics
from tradingos_api.core.scheduler import get_scheduler_status
from tradingos_api.db.session import get_db
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.schemas.ops import (
    CostBudgetStatusResponse,
    JobRunSummary,
    LatencyStatsResponse,
    MetricsResponse,
    SchedulerStatusResponse,
)
from tradingos_api.services.cost_budget import get_todays_llm_spend_usd
from tradingos_api.services.order_authority import is_kill_switch_active

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    snapshot = request_metrics.snapshot()
    return MetricsResponse(
        uptime_seconds=snapshot["uptime_seconds"],
        total_requests=snapshot["total_requests"],
        status_class_counts=snapshot["status_class_counts"],
        latency=LatencyStatsResponse(**snapshot["latency"]),
    )


@router.get("/job-runs", response_model=list[JobRunSummary])
def list_job_runs(db: Session = Depends(get_db), limit: int = 20) -> list[JobRunSummary]:
    """Most-recent-first `MorningPlanRun` rows — the job dashboard's
    content. `limit` is capped at 100 so a careless client can't force
    an unbounded scan of the whole run history."""
    capped_limit = min(max(limit, 1), 100)
    runs = db.scalars(
        select(MorningPlanRun).order_by(MorningPlanRun.started_at.desc()).limit(capped_limit)
    ).all()
    return [
        JobRunSummary(
            id=run.id,
            plan_date=run.plan_date,
            status=run.status,
            triggered_by=run.triggered_by,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=(
                (run.completed_at - run.started_at).total_seconds() if run.completed_at else None
            ),
            error_detail=run.error_detail,
        )
        for run in runs
    ]


@router.get("/scheduler", response_model=SchedulerStatusResponse)
def get_scheduler_status_route() -> SchedulerStatusResponse:
    """Read-only status for `core/scheduler.py`'s in-process APScheduler
    (Revision Prompt 16, task: real always-on scheduler/worker
    process) — what the job dashboard shows instead of the old "no
    always-on scheduler is deployed yet" copy."""
    status = get_scheduler_status()
    return SchedulerStatusResponse(
        running=status.running,
        tick_interval_seconds=status.tick_interval_seconds,
        tick_count=status.tick_count,
        last_tick_at=status.last_tick_at,
        last_tick_error=status.last_tick_error,
    )


@router.get("/cost-budget", response_model=CostBudgetStatusResponse)
def get_cost_budget_status(db: Session = Depends(get_db)) -> CostBudgetStatusResponse:
    """Read-only status — the actual enforcement runs inline in
    `services/committee_orchestrator.py::run_committee()`
    (`services/cost_budget.py::check_and_enforce_cost_budget`), not
    here. This endpoint never activates or deactivates anything."""
    now = datetime.now(UTC)
    budget = get_settings().daily_llm_cost_budget_usd
    spend = get_todays_llm_spend_usd(db, now=now)
    return CostBudgetStatusResponse(
        daily_spend_usd=spend,
        daily_budget_usd=budget,
        budget_remaining_usd=max(budget - spend, Decimal("0")),
        kill_switch_active=is_kill_switch_active(db),
        as_of=now,
    )


__all__ = ["router"]
