from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    EventBacktestDatasetSplit,
    EventBacktestExitReason,
    EventBacktestStrategyKey,
    EventBacktestTradeLane,
)


class BacktestRunRequest(BaseModel):
    """Every field mirrors `services/backtest_engine.py::BacktestRunConfig`
    1:1 — a request is the exact, reproducible configuration for one run
    (principle 8/9), defaults matching Prompt 13's locked baseline
    scenario."""

    strategy_key: EventBacktestStrategyKey
    initial_equity: Decimal = Decimal(10000)
    start: date = date(2024, 8, 1)
    end: date = date(2026, 7, 31)
    universe_start: date = date(2024, 8, 1)
    universe_end: date = date(2026, 7, 31)
    score_threshold: int = 5
    expected_move_threshold_pct: Decimal = Decimal(4)
    normal_risk_pct: Decimal = Decimal("0.50")
    speculative_risk_pct: Decimal = Decimal("0.25")
    max_position_pct: Decimal = Decimal("15.00")
    max_sector_pct: Decimal = Decimal("25.00")
    max_concurrent_positions: int = 3
    fee_bps: Decimal = Decimal(5)
    max_holding_days: int = 10
    entry_window_days: int = 3
    min_analyst_estimates: int = 3
    min_avg_daily_dollar_volume: Decimal = Decimal(50_000_000)
    seed: int = 42
    universe_tickers: list[str] | None = None


class TradeStatsResponse(BaseModel):
    num_trades: int
    num_wins: int
    num_losses: int
    num_breakeven: int
    win_rate_pct: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    payoff_ratio: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None

    model_config = {"from_attributes": True}


class DrawdownResponse(BaseModel):
    max_drawdown_pct: Decimal
    peak_index: int | None
    trough_index: int | None
    recovery_index: int | None
    recovery_periods: int | None

    model_config = {"from_attributes": True}


class EquityPointResponse(BaseModel):
    as_of: date
    equity: Decimal


class BacktestTradeResponse(BaseModel):
    id: uuid.UUID
    instrument_id: uuid.UUID
    lane: EventBacktestTradeLane
    event_date: date | None
    fiscal_period: str | None
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    quantity: Decimal
    fees_usd: Decimal
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: EventBacktestExitReason
    score: Decimal | None
    expected_move_pct: Decimal | None

    model_config = {"from_attributes": True}


class BacktestRunSummaryResponse(BaseModel):
    id: uuid.UUID
    strategy_key: EventBacktestStrategyKey
    dataset_split: EventBacktestDatasetSplit
    walk_forward_window_label: str | None
    date_range_start: date
    date_range_end: date
    is_golden_regression: bool
    created_at: datetime
    trade_stats: TradeStatsResponse
    drawdown: DrawdownResponse
    total_return_pct: Decimal | None
    benchmark_return_pct: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None


class BacktestRunDetailResponse(BacktestRunSummaryResponse):
    config: dict[str, Any]
    equity_curve: list[EquityPointResponse]
    trades: list[BacktestTradeResponse]


class BacktestComparisonResponse(BaseModel):
    runs: list[BacktestRunSummaryResponse]


class SweepPointResponse(BaseModel):
    label: str
    trade_stats: TradeStatsResponse
    total_return_pct: Decimal | None


class WalkForwardWindowResponse(BaseModel):
    split: EventBacktestDatasetSplit
    label: str
    start: date
    end: date
    trade_stats: TradeStatsResponse
    total_return_pct: Decimal | None


class BaselineReproductionResponse(BaseModel):
    locked_window: SweepPointResponse
    wide_window: SweepPointResponse
    targets: dict[str, Decimal | int]
    deviation_explanation: str


class GoNoGoReportResponse(BaseModel):
    baseline: BaselineReproductionResponse
    strategy_comparison: list[SweepPointResponse]
    score_threshold_sensitivity: list[SweepPointResponse]
    expected_move_threshold_sensitivity: list[SweepPointResponse]
    risk_budget_sensitivity: list[SweepPointResponse]
    lane_variant_comparison: list[SweepPointResponse]
    semiconductor_concentration: SweepPointResponse
    walk_forward: list[WalkForwardWindowResponse]
    by_year: list[SweepPointResponse]
    by_sector: list[SweepPointResponse]
    bias_and_quality_caveats: list[str]
    recommendation: str


__all__ = [
    "BacktestComparisonResponse",
    "BacktestRunDetailResponse",
    "BacktestRunRequest",
    "BacktestRunSummaryResponse",
    "BacktestTradeResponse",
    "BaselineReproductionResponse",
    "DrawdownResponse",
    "EquityPointResponse",
    "GoNoGoReportResponse",
    "SweepPointResponse",
    "TradeStatsResponse",
    "WalkForwardWindowResponse",
]
