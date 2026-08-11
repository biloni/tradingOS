"""Job dashboard + metrics response shapes (Revision Prompt 16)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import MorningPlanRunStatus


class LatencyStatsResponse(BaseModel):
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    sample_size: int


class MetricsResponse(BaseModel):
    uptime_seconds: float
    total_requests: int
    status_class_counts: dict[str, int]
    latency: LatencyStatsResponse


class JobRunSummary(BaseModel):
    """One `MorningPlanRun` row — the one recurring "job" this app
    actually has today (see `docs/OPERATIONS.md`'s scheduler runbook).
    `duration_seconds` is `None` while `status == RUNNING`."""

    id: uuid.UUID
    plan_date: date
    status: MorningPlanRunStatus
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    error_detail: str | None


class SchedulerStatusResponse(BaseModel):
    """`core/scheduler.py`'s in-process APScheduler status (Revision
    Prompt 16, task: real always-on scheduler/worker process).
    `running=False` is the honest state whenever `SCHEDULER_ENABLED=false`
    or the process's ASGI lifespan hasn't started it — never faked as
    healthy."""

    running: bool
    tick_interval_seconds: int
    tick_count: int
    last_tick_at: datetime | None
    last_tick_error: str | None


class CostBudgetStatusResponse(BaseModel):
    """`daily_spend_usd`/`daily_budget_usd` serialize as strings
    (ADR-031: money fields never serialize as native JSON numbers)."""

    daily_spend_usd: Decimal
    daily_budget_usd: Decimal
    budget_remaining_usd: Decimal
    kill_switch_active: bool
    as_of: datetime


__all__ = [
    "CostBudgetStatusResponse",
    "JobRunSummary",
    "LatencyStatsResponse",
    "MetricsResponse",
    "SchedulerStatusResponse",
]
