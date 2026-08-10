"""Event-driven backtest engine (Revision Prompt 13). New prefix
(`/api/v1/event-backtests`, not `/api/v1/backtests`) to avoid confusion
with the legacy read-only `routers/backtests.py` — that router serves
the shipped-MVP's `BacktestRun`/`BacktestTrade` seed fixture, this one
runs and persists a real simulation against `EventBacktestRun`/
`EventBacktestTrade` (see docs/DECISIONS.md's Prompt 13 ADR for why
these are separate tables rather than one extended)."""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.backtest_v2 import EventBacktestRun
from tradingos_api.schemas.backtest_v2 import (
    BacktestComparisonResponse,
    BacktestRunDetailResponse,
    BacktestRunRequest,
    BacktestRunSummaryResponse,
    BaselineReproductionResponse,
    DrawdownResponse,
    EquityPointResponse,
    GoNoGoReportResponse,
    SweepPointResponse,
    TradeStatsResponse,
    WalkForwardWindowResponse,
)
from tradingos_api.schemas.common import Page
from tradingos_api.services.backtest_data import DEFAULT_UNIVERSE_TICKERS
from tradingos_api.services.backtest_engine import BacktestResult, BacktestRunConfig, run_backtest
from tradingos_api.services.backtest_persistence import (
    get_backtest_run,
    list_backtest_runs,
    list_backtest_trades,
    save_backtest_run,
)
from tradingos_api.services.backtest_validation import (
    BaselineReproductionReport,
    GoNoGoReport,
    SweepPoint,
    WalkForwardWindow,
    build_go_no_go_report,
    reproduce_baseline_scenario,
)

router = APIRouter(prefix="/api/v1/event-backtests", tags=["event-backtests"])


def _config_request_to_dataclass(payload: BacktestRunRequest) -> BacktestRunConfig:
    return BacktestRunConfig(
        strategy_key=payload.strategy_key,
        initial_equity=payload.initial_equity,
        start=payload.start,
        end=payload.end,
        universe_start=payload.universe_start,
        universe_end=payload.universe_end,
        score_threshold=payload.score_threshold,
        expected_move_threshold_pct=payload.expected_move_threshold_pct,
        normal_risk_pct=payload.normal_risk_pct,
        speculative_risk_pct=payload.speculative_risk_pct,
        max_position_pct=payload.max_position_pct,
        max_sector_pct=payload.max_sector_pct,
        max_concurrent_positions=payload.max_concurrent_positions,
        fee_bps=payload.fee_bps,
        max_holding_days=payload.max_holding_days,
        entry_window_days=payload.entry_window_days,
        min_analyst_estimates=payload.min_analyst_estimates,
        min_avg_daily_dollar_volume=payload.min_avg_daily_dollar_volume,
        seed=payload.seed,
        universe_tickers=tuple(payload.universe_tickers)
        if payload.universe_tickers
        else DEFAULT_UNIVERSE_TICKERS,
    )


def _summary_from_live_result(
    run: EventBacktestRun, result: BacktestResult
) -> BacktestRunSummaryResponse:
    stats = result.trade_stats
    dd = result.drawdown
    return BacktestRunSummaryResponse(
        id=run.id,
        strategy_key=run.strategy_key,
        dataset_split=run.dataset_split,
        walk_forward_window_label=run.walk_forward_window_label,
        date_range_start=run.date_range_start,
        date_range_end=run.date_range_end,
        is_golden_regression=run.is_golden_regression,
        created_at=run.created_at,
        trade_stats=TradeStatsResponse.model_validate(stats),
        drawdown=DrawdownResponse.model_validate(dd),
        total_return_pct=result.total_return_pct,
        benchmark_return_pct=result.benchmark_return_pct,
        sharpe_ratio=result.sharpe_ratio,
        sortino_ratio=result.sortino_ratio,
    )


def _decimal(value: Any) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _summary_from_persisted_run(run: EventBacktestRun) -> BacktestRunSummaryResponse:
    s = run.results_summary
    trade_stats = TradeStatsResponse(
        num_trades=s["num_trades"],
        num_wins=s["num_wins"],
        num_losses=s["num_losses"],
        num_breakeven=s["num_trades"] - s["num_wins"] - s["num_losses"],
        win_rate_pct=_decimal(s.get("win_rate_pct")),
        avg_win=_decimal(s.get("avg_win")),
        avg_loss=_decimal(s.get("avg_loss")),
        payoff_ratio=_decimal(s.get("payoff_ratio")),
        profit_factor=_decimal(s.get("profit_factor")),
        expectancy=_decimal(s.get("expectancy")),
    )
    drawdown = DrawdownResponse(
        max_drawdown_pct=_decimal(s.get("max_drawdown_pct")) or Decimal(0),
        peak_index=None,
        trough_index=None,
        recovery_index=None,
        recovery_periods=s.get("recovery_periods"),
    )
    return BacktestRunSummaryResponse(
        id=run.id,
        strategy_key=run.strategy_key,
        dataset_split=run.dataset_split,
        walk_forward_window_label=run.walk_forward_window_label,
        date_range_start=run.date_range_start,
        date_range_end=run.date_range_end,
        is_golden_regression=run.is_golden_regression,
        created_at=run.created_at,
        trade_stats=trade_stats,
        drawdown=drawdown,
        total_return_pct=_decimal(s.get("total_return_pct")),
        benchmark_return_pct=_decimal(s.get("benchmark_return_pct")),
        sharpe_ratio=_decimal(s.get("sharpe_ratio")),
        sortino_ratio=_decimal(s.get("sortino_ratio")),
    )


def _sweep_point_response(point: SweepPoint) -> SweepPointResponse:
    return SweepPointResponse(
        label=point.label,
        trade_stats=TradeStatsResponse.model_validate(point.result.trade_stats),
        total_return_pct=point.result.total_return_pct,
    )


def _walk_forward_response(window: WalkForwardWindow) -> WalkForwardWindowResponse:
    return WalkForwardWindowResponse(
        split=window.split,
        label=window.label,
        start=window.start,
        end=window.end,
        trade_stats=TradeStatsResponse.model_validate(window.result.trade_stats),
        total_return_pct=window.result.total_return_pct,
    )


def _baseline_response(report: BaselineReproductionReport) -> BaselineReproductionResponse:
    return BaselineReproductionResponse(
        locked_window=SweepPointResponse(
            label="LOCKED_SCENARIO_WINDOW",
            trade_stats=TradeStatsResponse.model_validate(report.locked_window_result.trade_stats),
            total_return_pct=report.locked_window_result.total_return_pct,
        ),
        wide_window=SweepPointResponse(
            label="FULL_SYNTHETIC_WINDOW",
            trade_stats=TradeStatsResponse.model_validate(report.wide_window_result.trade_stats),
            total_return_pct=report.wide_window_result.total_return_pct,
        ),
        targets=report.targets,
        deviation_explanation=report.deviation_explanation,
    )


@router.post("/run", response_model=BacktestRunDetailResponse, status_code=201)
def trigger_backtest_run(
    payload: BacktestRunRequest, db: Session = Depends(get_db)
) -> BacktestRunDetailResponse:
    """Runs and persists one backtest — "reproducible run configuration":
    the exact request body is snapshotted onto `EventBacktestRun.config`,
    so replaying this same body later reproduces this same run."""
    config = _config_request_to_dataclass(payload)
    result = run_backtest(db, config)
    run = save_backtest_run(db, result)
    db.commit()
    trades = list_backtest_trades(db, run.id)
    summary = _summary_from_live_result(run, result)
    return BacktestRunDetailResponse(
        **summary.model_dump(),
        config=run.config,
        equity_curve=[EquityPointResponse(as_of=d, equity=v) for d, v in result.equity_curve],
        trades=[
            {
                "id": t.id,
                "instrument_id": t.instrument_id,
                "lane": t.lane,
                "event_date": t.event_date,
                "fiscal_period": t.fiscal_period,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "fees_usd": t.fees_usd,
                "pnl_usd": t.pnl_usd,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
                "score": t.score,
                "expected_move_pct": t.expected_move_pct,
            }
            for t in trades
        ],
    )


@router.get("", response_model=Page[BacktestRunSummaryResponse])
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[BacktestRunSummaryResponse]:
    rows, total = list_backtest_runs(db, limit=limit, offset=offset)
    items = [_summary_from_persisted_run(r) for r in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/compare", response_model=BacktestComparisonResponse)
def compare_runs(
    run_ids: list[uuid.UUID] = Query(..., min_length=2, max_length=8),
    db: Session = Depends(get_db),
) -> BacktestComparisonResponse:
    """Side-by-side comparison — 2 or more runs' summary metrics, the
    same underlying `EventBacktestRun` rows the detail/download
    endpoints serve, never a separately recomputed comparison.
    Registered before `/{run_id}` (a static path must be registered
    ahead of a same-depth dynamic path, or Starlette's route matching
    swallows it as a `run_id` value — verified live, see
    docs/TEST_EVIDENCE.md's Prompt 13 entry)."""
    runs: list[BacktestRunSummaryResponse] = []
    for run_id in run_ids:
        run = get_backtest_run(db, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Backtest run {run_id} not found.")
        runs.append(_summary_from_persisted_run(run))
    return BacktestComparisonResponse(runs=runs)


@router.get("/reports/baseline-reproduction", response_model=BaselineReproductionResponse)
def get_baseline_reproduction(db: Session = Depends(get_db)) -> BaselineReproductionResponse:
    """The locked regression scenario, run live against real state — see
    `services/backtest_validation.py`'s module docstring for exactly why
    the locked window's trade count is too sparse to compare against the
    stated target, and why the wide-window run is reported alongside it."""
    report = reproduce_baseline_scenario(db)
    return _baseline_response(report)


@router.get("/reports/go-no-go", response_model=GoNoGoReportResponse)
def get_go_no_go_report(db: Session = Depends(get_db)) -> GoNoGoReportResponse:
    """Runs the full validation grid live (score/expected-move/risk
    sweeps, lane-variant comparison, semiconductor-concentration subset,
    walk-forward, by-year/by-sector breakdowns) and assembles the go/
    no-go recommendation — read-only, no run is persisted by this
    endpoint (persist a run explicitly via `POST /run` if a specific
    result needs to be kept for drill-down)."""
    report: GoNoGoReport = build_go_no_go_report(db)
    return GoNoGoReportResponse(
        baseline=_baseline_response(report.baseline),
        strategy_comparison=[_sweep_point_response(p) for p in report.strategy_comparison],
        score_threshold_sensitivity=[
            _sweep_point_response(p) for p in report.score_threshold_sensitivity
        ],
        expected_move_threshold_sensitivity=[
            _sweep_point_response(p) for p in report.expected_move_threshold_sensitivity
        ],
        risk_budget_sensitivity=[_sweep_point_response(p) for p in report.risk_budget_sensitivity],
        lane_variant_comparison=[_sweep_point_response(p) for p in report.lane_variant_comparison],
        semiconductor_concentration=SweepPointResponse(
            label="SEMICONDUCTOR_SUBSET",
            trade_stats=TradeStatsResponse.model_validate(
                report.semiconductor_concentration.trade_stats
            ),
            total_return_pct=report.semiconductor_concentration.total_return_pct,
        ),
        walk_forward=[_walk_forward_response(w) for w in report.walk_forward],
        by_year=[_sweep_point_response(p) for p in report.by_year],
        by_sector=[_sweep_point_response(p) for p in report.by_sector],
        bias_and_quality_caveats=report.bias_and_quality_caveats,
        recommendation=report.recommendation,
    )


@router.get("/{run_id}", response_model=BacktestRunDetailResponse)
def get_run_detail(run_id: uuid.UUID, db: Session = Depends(get_db)) -> BacktestRunDetailResponse:
    """The trade drill-down screen — every simulated trade for this run,
    plus its full config snapshot for reproducibility."""
    run = get_backtest_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    trades = list_backtest_trades(db, run_id)
    summary = _summary_from_persisted_run(run)
    equity_curve = [
        EquityPointResponse(as_of=point["as_of"], equity=Decimal(point["equity"]))
        for point in run.results_summary.get("equity_curve", [])
    ]
    return BacktestRunDetailResponse(
        **summary.model_dump(),
        config=run.config,
        equity_curve=equity_curve,
        trades=[
            {
                "id": t.id,
                "instrument_id": t.instrument_id,
                "lane": t.lane,
                "event_date": t.event_date,
                "fiscal_period": t.fiscal_period,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "fees_usd": t.fees_usd,
                "pnl_usd": t.pnl_usd,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
                "score": t.score,
                "expected_move_pct": t.expected_move_pct,
            }
            for t in trades
        ],
    )


@router.get("/{run_id}/download")
def download_run_trades(run_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """Downloadable output — the run's full trade log as CSV."""
    run = get_backtest_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    trades = list_backtest_trades(db, run_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "instrument_id", "lane", "event_date", "fiscal_period", "entry_date", "entry_price",
            "exit_date", "exit_price", "quantity", "fees_usd", "pnl_usd", "pnl_pct", "exit_reason",
            "score", "expected_move_pct",
        ]
    )  # fmt: skip
    for t in trades:
        writer.writerow(
            [
                t.instrument_id, t.lane.value, t.event_date, t.fiscal_period, t.entry_date,
                t.entry_price, t.exit_date, t.exit_price, t.quantity, t.fees_usd, t.pnl_usd,
                t.pnl_pct, t.exit_reason.value, t.score, t.expected_move_pct,
            ]
        )  # fmt: skip
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=backtest_{run_id}_trades.csv"},
    )


__all__ = ["router"]
