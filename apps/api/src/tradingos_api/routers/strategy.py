from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.strategy_version import StrategyVersion
from tradingos_api.schemas.backtest import BacktestRunOut
from tradingos_api.schemas.strategy import (
    StrategyBacktestParams,
    StrategyComparisonOut,
    StrategyVersionApproveRequest,
    StrategyVersionCreateRequest,
    StrategyVersionOut,
    StrategyVersionRejectRequest,
)
from tradingos_api.services.backtest import DEFAULT_BACKTEST_LOOKBACK_DAYS
from tradingos_api.services.strategy import (
    approve_strategy_version,
    get_or_create_default_strategy_version,
    propose_strategy_version,
    reject_strategy_version,
    run_comparison,
)

router = APIRouter(prefix="/api/v1/strategy-versions", tags=["strategy-versions"])


def _get_strategy_version_or_404(session: Session, version_id: int) -> StrategyVersion:
    version = session.get(StrategyVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Unknown strategy version: {version_id}")
    return version


def _to_out(version: StrategyVersion) -> StrategyVersionOut:
    return StrategyVersionOut.model_validate(version)


def _resolve_date_range(params: StrategyBacktestParams) -> tuple[date, date]:
    end = params.date_range_end or date.today()
    start = params.date_range_start or (end - timedelta(days=DEFAULT_BACKTEST_LOOKBACK_DAYS))
    return start, end


def _backtest_kwargs(params: StrategyBacktestParams) -> dict[str, object]:
    return {
        "entry_score_threshold": params.entry_score_threshold,
        "exit_score_threshold": params.exit_score_threshold,
        "max_holding_days": params.max_holding_days,
        "position_size_pct": params.position_size_pct,
        "starting_cash": params.starting_cash,
        "benchmark_ticker": params.benchmark_ticker,
    }


@router.post("", response_model=StrategyVersionOut, status_code=201)
def propose_version(
    body: StrategyVersionCreateRequest, session: Annotated[Session, Depends(get_db)]
) -> StrategyVersionOut:
    """A proposal is a user/operator-submitted candidate config (ADR-026)
    — never touches the currently active version."""
    version = propose_strategy_version(session, body.name, body.config.model_dump(mode="json"))
    return _to_out(version)


@router.post("/{version_id}/compare", response_model=StrategyComparisonOut)
def compare_version(
    version_id: int,
    body: StrategyBacktestParams,
    session: Annotated[Session, Depends(get_db)],
) -> StrategyComparisonOut:
    """Read-only and repeatable — runs a fresh backtest for both the
    candidate and the currently active version with identical params
    (ADR-028), never changing the candidate's status."""
    candidate = _get_strategy_version_or_404(session, version_id)
    active = get_or_create_default_strategy_version(session)
    start, end = _resolve_date_range(body)

    try:
        candidate_run, active_run, delta = run_comparison(
            session, candidate, active, start, end, **_backtest_kwargs(body)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StrategyComparisonOut(
        candidate_backtest=BacktestRunOut.model_validate(candidate_run),
        active_backtest=BacktestRunOut.model_validate(active_run),
        delta=delta,
    )


@router.post("/{version_id}/approve", response_model=StrategyVersionOut)
def approve_version(
    version_id: int,
    body: StrategyVersionApproveRequest,
    session: Annotated[Session, Depends(get_db)],
) -> StrategyVersionOut:
    """The explicit human approval action (principle 16) — requires the
    candidate to be PROPOSED; re-runs the comparison itself rather than
    trusting a prior /compare call (ADR-028)."""
    candidate = _get_strategy_version_or_404(session, version_id)
    start, end = _resolve_date_range(body)

    try:
        version = approve_strategy_version(
            session, candidate, start, end, body.comment, **_backtest_kwargs(body)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_out(version)


@router.post("/{version_id}/reject", response_model=StrategyVersionOut)
def reject_version(
    version_id: int,
    body: StrategyVersionRejectRequest,
    session: Annotated[Session, Depends(get_db)],
) -> StrategyVersionOut:
    candidate = _get_strategy_version_or_404(session, version_id)

    try:
        version = reject_strategy_version(session, candidate, body.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_out(version)


@router.get("", response_model=list[StrategyVersionOut])
def list_versions(session: Annotated[Session, Depends(get_db)]) -> list[StrategyVersionOut]:
    versions = (
        session.execute(select(StrategyVersion).order_by(StrategyVersion.created_at.desc()))
        .scalars()
        .all()
    )
    return [_to_out(v) for v in versions]


@router.get("/{version_id}", response_model=StrategyVersionOut)
def get_version(
    version_id: int, session: Annotated[Session, Depends(get_db)]
) -> StrategyVersionOut:
    version = _get_strategy_version_or_404(session, version_id)
    return _to_out(version)
