from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.backtest_run import BacktestRun
from tradingos_api.schemas.backtest import BacktestCreateRequest, BacktestRunOut
from tradingos_api.services.backtest import DEFAULT_BACKTEST_LOOKBACK_DAYS, run_backtest

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


def _get_backtest_run_or_404(session: Session, run_id: int) -> BacktestRun:
    run = session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown backtest run: {run_id}")
    return run


def _to_out(run: BacktestRun) -> BacktestRunOut:
    return BacktestRunOut.model_validate(run)


@router.post("", response_model=BacktestRunOut, status_code=201)
def create_backtest(
    body: BacktestCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> BacktestRunOut:
    """Runs synchronously (ADR-022..025) — the full seeded universe over
    ~2 years is cheap enough that no background job is warranted yet."""
    end = body.date_range_end or date.today()
    start = body.date_range_start or (end - timedelta(days=DEFAULT_BACKTEST_LOOKBACK_DAYS))

    try:
        run = run_backtest(
            session,
            date_range_start=start,
            date_range_end=end,
            strategy_version_id=body.strategy_version_id,
            entry_score_threshold=body.entry_score_threshold,
            exit_score_threshold=body.exit_score_threshold,
            max_holding_days=body.max_holding_days,
            position_size_pct=body.position_size_pct,
            starting_cash=body.starting_cash,
            benchmark_ticker=body.benchmark_ticker,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_out(run)


@router.get("", response_model=list[BacktestRunOut])
def list_backtests(session: Annotated[Session, Depends(get_db)]) -> list[BacktestRunOut]:
    runs = (
        session.execute(select(BacktestRun).order_by(BacktestRun.created_at.desc())).scalars().all()
    )
    return [_to_out(run) for run in runs]


@router.get("/{run_id}", response_model=BacktestRunOut)
def get_backtest(run_id: int, session: Annotated[Session, Depends(get_db)]) -> BacktestRunOut:
    run = _get_backtest_run_or_404(session, run_id)
    return _to_out(run)
