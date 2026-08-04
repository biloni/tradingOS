from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PerformanceSnapshotResponse(BaseModel):
    account_id: uuid.UUID
    period_start: date
    period_end: date
    realized_pnl: Decimal
    win_rate: Decimal | None
    avg_r_multiple: Decimal | None
    max_drawdown_pct: Decimal | None

    model_config = {"from_attributes": True}


class BenchmarkSnapshotResponse(BaseModel):
    benchmark_ticker: str
    period_start: date
    period_end: date
    return_pct: Decimal

    model_config = {"from_attributes": True}


class PerformanceComparisonResponse(BaseModel):
    account: PerformanceSnapshotResponse | None
    benchmark: BenchmarkSnapshotResponse | None
