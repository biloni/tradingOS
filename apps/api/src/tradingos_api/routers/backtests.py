"""Backtests (docs/API_CONTRACTS.md area 11). Read-only this pass — no
new backtest can be *run* yet since that requires the scoring/replay
engine to be ported onto the new schema (services/backtest.py was
retired with the rest of the shipped MVP's business logic this phase,
ADR-044) — the seed fixtures provide one representative run to read.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.backtest import BacktestRun, BacktestTrade
from tradingos_api.schemas.backtests import BacktestRunResponse, BacktestTradeResponse
from tradingos_api.schemas.common import Page

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


def _run_response(db: Session, run: BacktestRun) -> BacktestRunResponse:
    trades = db.scalars(select(BacktestTrade).where(BacktestTrade.backtest_run_id == run.id)).all()
    return BacktestRunResponse(
        id=run.id,
        strategy_version_id=run.strategy_version_id,
        date_range_start=run.date_range_start,
        date_range_end=run.date_range_end,
        parameters=run.parameters,
        results_summary=run.results_summary,
        created_at=run.created_at,
        trades=[BacktestTradeResponse.model_validate(t) for t in trades],
    )


@router.get("", response_model=Page[BacktestRunResponse])
def list_backtests(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[BacktestRunResponse]:
    all_rows = db.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc())).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    items = [_run_response(db, r) for r in page_rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=BacktestRunResponse)
def get_backtest(run_id: uuid.UUID, db: Session = Depends(get_db)) -> BacktestRunResponse:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return _run_response(db, run)
