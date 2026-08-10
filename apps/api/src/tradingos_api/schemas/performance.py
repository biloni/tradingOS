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


# --------------------------------------------------------------------
# Revision Prompt 12 — portfolio/strategy/recommendation-vs-reality/
# morning-plan-quality analytics. Every field mirrors a
# `services/performance_*.py` dataclass 1:1 (`model_config`'s
# `from_attributes=True` reads a dataclass instance directly, the same
# as it would an ORM row) so the response schema is never a second,
# independently-drifting description of the same computation.
# --------------------------------------------------------------------


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
    cash: Decimal
    market_value: Decimal
    equity: Decimal

    model_config = {"from_attributes": True}


class PortfolioPerformanceResponse(BaseModel):
    as_of: date
    equity: Decimal | None
    cash: Decimal | None
    market_value: Decimal | None
    daily_return_pct: Decimal | None
    weekly_return_pct: Decimal | None
    monthly_return_pct: Decimal | None
    ytd_return_pct: Decimal | None
    inception_return_pct: Decimal | None
    time_weighted_return_pct: Decimal | None
    money_weighted_return_pct: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    trade_stats: TradeStatsResponse
    annualized_volatility_pct: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    drawdown: DrawdownResponse
    beta_vs_spy: Decimal | None
    alpha_vs_spy_pct: Decimal | None
    gross_exposure_pct: Decimal | None
    concentration_hhi: Decimal
    turnover_pct_30d: Decimal | None
    cash_history: list[EquityPointResponse]
    sample_size_days: int
    calculation_version: str

    model_config = {"from_attributes": True}


class GroupedTradeStatsResponse(BaseModel):
    group_key: str
    stats: TradeStatsResponse

    model_config = {"from_attributes": True}


class PolicyVetoOutcomesResponse(BaseModel):
    total_evaluations: int
    authorized: int
    denied: int
    denial_reasons: dict[str, int]

    model_config = {"from_attributes": True}


class RecommendationRealityRowResponse(BaseModel):
    recommendation_id: uuid.UUID
    mode: str
    status: str
    disposition: str
    actual_pnl: Decimal | None
    hypothetical_pnl_pct: Decimal | None
    r_multiple: Decimal | None
    committee_session_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class MorningPlanQualitySummaryResponse(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    on_time_rate_pct: Decimal | None
    complete_final_rate_pct: Decimal | None
    check_pass_rate_pct: Decimal | None
    stale_data_check_pass_rate_pct: Decimal | None
    action_days: int
    no_action_days: int

    model_config = {"from_attributes": True}


class SectionResultsResponse(BaseModel):
    section_key: str
    stats: TradeStatsResponse

    model_config = {"from_attributes": True}


class ApprovalConversionResponse(BaseModel):
    total_approvals: int
    approved: int
    denied_or_expired: int
    approval_to_submission_rate_pct: Decimal | None
    denial_reasons: dict[str, int]

    model_config = {"from_attributes": True}


class EquityCurveChartResponse(BaseModel):
    account_points: list[EquityPointResponse]
    benchmark_points: list[EquityPointResponse]


class DrawdownChartPoint(BaseModel):
    as_of: date
    drawdown_pct: Decimal


class ScoreThresholdSensitivityPoint(BaseModel):
    score_threshold: int
    stats: TradeStatsResponse


class MorningRecommendationFunnelResponse(BaseModel):
    plans_generated: int
    items_surfaced: int
    action_items: int
    approvals_requested: int
    approvals_granted: int
    orders_submitted: int
