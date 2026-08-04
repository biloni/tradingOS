"""Performance and benchmarks (docs/API_CONTRACTS.md area 8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.execution import Account
from tradingos_api.models.learning import BenchmarkSnapshot, PerformanceSnapshot
from tradingos_api.schemas.performance import (
    BenchmarkSnapshotResponse,
    PerformanceComparisonResponse,
    PerformanceSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


@router.get("/accounts/{account_id}", response_model=list[PerformanceSnapshotResponse])
def list_performance_snapshots(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[PerformanceSnapshotResponse]:
    if db.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    rows = db.scalars(
        select(PerformanceSnapshot)
        .where(PerformanceSnapshot.account_id == account_id)
        .order_by(PerformanceSnapshot.period_end.desc())
    ).all()
    return [PerformanceSnapshotResponse.model_validate(r) for r in rows]


@router.get("/compare/{account_id}", response_model=PerformanceComparisonResponse)
def compare_to_benchmark(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    benchmark_ticker: str = Query(default="SPY"),
) -> PerformanceComparisonResponse:
    if db.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    latest_perf = db.scalar(
        select(PerformanceSnapshot)
        .where(PerformanceSnapshot.account_id == account_id)
        .order_by(PerformanceSnapshot.period_end.desc())
    )
    benchmark = None
    if latest_perf is not None:
        benchmark = db.scalar(
            select(BenchmarkSnapshot).where(
                BenchmarkSnapshot.benchmark_ticker == benchmark_ticker,
                BenchmarkSnapshot.period_start == latest_perf.period_start,
                BenchmarkSnapshot.period_end == latest_perf.period_end,
            )
        )
    return PerformanceComparisonResponse(
        account=PerformanceSnapshotResponse.model_validate(latest_perf) if latest_perf else None,
        benchmark=BenchmarkSnapshotResponse.model_validate(benchmark) if benchmark else None,
    )
