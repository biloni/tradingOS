"""Persists `BacktestResult` into `EventBacktestRun`/`EventBacktestTrade`
(Revision Prompt 13) — "build reproducible run configuration, trade
drill-down, comparison, and downloadable output." `config` and
`results_summary` are plain-JSON snapshots of the dataclasses
`services/backtest_engine.py` already computed; this module does no
math of its own, only serialization and storage, matching
`services/performance_coach.py`'s "the service computes, the router
formats" boundary discipline extended one layer further here.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.backtest_v2 import EventBacktestRun, EventBacktestTrade
from tradingos_api.models.enums import EventBacktestDatasetSplit
from tradingos_api.services.backtest_engine import BacktestResult


def _decimal_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _config_to_json(result: BacktestResult) -> dict[str, Any]:
    config = result.config
    return {
        "strategy_key": config.strategy_key.value,
        "initial_equity": str(config.initial_equity),
        "start": config.start.isoformat(),
        "end": config.end.isoformat(),
        "universe_start": config.universe_start.isoformat(),
        "universe_end": config.universe_end.isoformat(),
        "score_threshold": config.score_threshold,
        "expected_move_threshold_pct": str(config.expected_move_threshold_pct),
        "normal_risk_pct": str(config.normal_risk_pct),
        "speculative_risk_pct": str(config.speculative_risk_pct),
        "max_position_pct": str(config.max_position_pct),
        "max_sector_pct": str(config.max_sector_pct),
        "max_concurrent_positions": config.max_concurrent_positions,
        "fee_bps": str(config.fee_bps),
        "max_holding_days": config.max_holding_days,
        "entry_window_days": config.entry_window_days,
        "min_analyst_estimates": config.min_analyst_estimates,
        "min_avg_daily_dollar_volume": str(config.min_avg_daily_dollar_volume),
        "max_liquidity_pct_of_adv": str(config.max_liquidity_pct_of_adv),
        "speculative_position_pct_cap": str(config.speculative_position_pct_cap),
        "slippage_bps": str(config.slippage_bps),
        "seed": config.seed,
        "universe_tickers": list(config.universe_tickers),
    }


def _summary_to_json(result: BacktestResult) -> dict[str, Any]:
    stats = result.trade_stats
    dd = result.drawdown
    return {
        "num_trades": stats.num_trades,
        "num_wins": stats.num_wins,
        "num_losses": stats.num_losses,
        "win_rate_pct": _decimal_or_none(stats.win_rate_pct),
        "avg_win": _decimal_or_none(stats.avg_win),
        "avg_loss": _decimal_or_none(stats.avg_loss),
        "payoff_ratio": _decimal_or_none(stats.payoff_ratio),
        "profit_factor": _decimal_or_none(stats.profit_factor),
        "expectancy": _decimal_or_none(stats.expectancy),
        "annualized_volatility_pct": _decimal_or_none(result.annualized_volatility_pct),
        "sharpe_ratio": _decimal_or_none(result.sharpe_ratio),
        "sortino_ratio": _decimal_or_none(result.sortino_ratio),
        "max_drawdown_pct": _decimal_or_none(dd.max_drawdown_pct),
        "recovery_periods": dd.recovery_periods,
        "total_return_pct": _decimal_or_none(result.total_return_pct),
        "benchmark_return_pct": _decimal_or_none(result.benchmark_return_pct),
        "events_seen": result.events_seen,
        "events_eligible": result.events_eligible,
        "equity_curve": [
            {"as_of": d.isoformat(), "equity": str(v)} for d, v in result.equity_curve
        ],
        "calculation_version": result.calculation_version,
    }


def save_backtest_run(
    db: Session,
    result: BacktestResult,
    *,
    dataset_split: EventBacktestDatasetSplit = EventBacktestDatasetSplit.FULL,
    walk_forward_window_label: str | None = None,
    is_golden_regression: bool = False,
) -> EventBacktestRun:
    run = EventBacktestRun(
        strategy_key=result.config.strategy_key,
        dataset_split=dataset_split,
        walk_forward_window_label=walk_forward_window_label,
        date_range_start=result.config.start,
        date_range_end=result.config.end,
        config=_config_to_json(result),
        results_summary=_summary_to_json(result),
        is_golden_regression=is_golden_regression,
    )
    db.add(run)
    db.flush()

    for trade in result.trades:
        db.add(
            EventBacktestTrade(
                backtest_run_id=run.id,
                instrument_id=trade.instrument_id,
                lane=trade.lane,
                event_date=trade.event_date,
                fiscal_period=trade.fiscal_period,
                entry_date=trade.entry_date,
                entry_price=trade.entry_price,
                exit_date=trade.exit_date,
                exit_price=trade.exit_price,
                quantity=Decimal(trade.quantity),
                fees_usd=trade.fees_usd,
                pnl_usd=trade.pnl_usd,
                pnl_pct=trade.pnl_pct,
                exit_reason=trade.exit_reason,
                score=trade.score,
                expected_move_pct=trade.expected_move_pct,
            )
        )
    db.flush()
    return run


def get_backtest_run(db: Session, run_id: uuid.UUID) -> EventBacktestRun | None:
    return db.get(EventBacktestRun, run_id)


def list_backtest_trades(db: Session, run_id: uuid.UUID) -> list[EventBacktestTrade]:
    return list(
        db.scalars(
            select(EventBacktestTrade)
            .where(EventBacktestTrade.backtest_run_id == run_id)
            .order_by(EventBacktestTrade.entry_date.asc())
        ).all()
    )


def list_backtest_runs(
    db: Session, *, limit: int = 50, offset: int = 0
) -> tuple[list[EventBacktestRun], int]:
    rows = db.scalars(select(EventBacktestRun).order_by(EventBacktestRun.created_at.desc())).all()
    return list(rows[offset : offset + limit]), len(rows)


__all__ = [
    "get_backtest_run",
    "list_backtest_runs",
    "list_backtest_trades",
    "save_backtest_run",
]
