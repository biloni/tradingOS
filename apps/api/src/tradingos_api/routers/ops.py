"""Job dashboard + metrics (Revision Prompt 16). Gated by
`require_session` like every other business router (`main.py`) —
unlike `/health`/`/ready`, this is operational data about the app's
own internals, not something an infra orchestrator with no credentials
needs to poll.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.metrics import request_metrics
from tradingos_api.db.session import get_db
from tradingos_api.models.morning_plan import MorningPlanRun
from tradingos_api.schemas.ops import JobRunSummary, LatencyStatsResponse, MetricsResponse

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


__all__ = ["router"]
