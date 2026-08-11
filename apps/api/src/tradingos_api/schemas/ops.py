"""Job dashboard + metrics response shapes (Revision Prompt 16)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

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


__all__ = ["JobRunSummary", "LatencyStatsResponse", "MetricsResponse"]
