"""Performance and benchmarks (docs/API_CONTRACTS.md area 8, extended
Revision Prompt 12 with real portfolio/strategy/recommendation-vs-
reality/morning-plan-quality analytics and their chart data)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import (
    BrokerSubmissionOutcome,
    OrderApprovalStatus,
    RecommendationConfidence,
    Timeframe,
    TradeStatus,
)
from tradingos_api.models.execution import Account, Trade
from tradingos_api.models.learning import BenchmarkSnapshot, PerformanceSnapshot
from tradingos_api.models.market_evidence import (
    EarningsHistoricalGap,
    EventExpectedMoveSnapshot,
    MarketBar,
)
from tradingos_api.models.morning_plan import MorningPlanItem, MorningPlanRun
from tradingos_api.models.order_authority import BrokerSubmissionAttempt, OrderApproval
from tradingos_api.models.recommendations import RecommendationAttribution, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.performance import (
    ApprovalConversionResponse,
    BenchmarkSnapshotResponse,
    DrawdownChartPoint,
    EquityCurveChartResponse,
    EquityPointResponse,
    GroupedTradeStatsResponse,
    MorningPlanQualitySummaryResponse,
    MorningRecommendationFunnelResponse,
    PerformanceComparisonResponse,
    PerformanceSnapshotResponse,
    PolicyVetoOutcomesResponse,
    PortfolioPerformanceResponse,
    RecommendationRealityRowResponse,
    ScoreThresholdSensitivityPoint,
    SectionResultsResponse,
    TradeStatsResponse,
)
from tradingos_api.services.morning_plan_quality import (
    get_approval_conversion,
    get_morning_plan_quality_summary,
    get_realized_results_by_section,
)
from tradingos_api.services.performance_coach import (
    MIN_SAMPLE_SIZE_FOR_SUMMARY,
    CoachSummaryResult,
    get_coach_summary,
)
from tradingos_api.services.performance_portfolio import get_equity_curve, get_portfolio_performance
from tradingos_api.services.performance_strategy import (
    get_lane_contribution,
    get_policy_veto_outcomes,
    get_pre_event_vs_post_confirmation_contribution,
    get_results_by_score_band,
    get_results_by_sector,
    get_score_threshold_sensitivity,
)
from tradingos_api.services.recommendation_reality import get_recommendation_reality_rows

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])
_SPY_TICKER = "SPY"


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


def _get_account_or_404(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


@router.get("/portfolio/{account_id}", response_model=PortfolioPerformanceResponse)
def get_portfolio_performance_view(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    as_of: date | None = Query(default=None),
) -> PortfolioPerformanceResponse:
    """Revision Prompt 12 — return, volatility, Sharpe/Sortino,
    drawdown/recovery, win rate/payoff/profit-factor/expectancy,
    beta/alpha vs. SPY, exposure/turnover/concentration, and cash
    history, all from `services/performance_portfolio.py`."""
    account = _get_account_or_404(db, account_id)
    result = get_portfolio_performance(db, account=account, as_of=as_of or datetime.now(UTC).date())
    return PortfolioPerformanceResponse.model_validate(result)


@router.get(
    "/strategy/{account_id}/lane-contribution", response_model=list[GroupedTradeStatsResponse]
)
def get_lane_contribution_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[GroupedTradeStatsResponse]:
    _get_account_or_404(db, account_id)
    return [
        GroupedTradeStatsResponse.model_validate(g)
        for g in get_lane_contribution(db, account_id=account_id)
    ]


@router.get(
    "/strategy/{account_id}/pre-post-confirmation",
    response_model=list[GroupedTradeStatsResponse],
)
def get_pre_post_confirmation_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[GroupedTradeStatsResponse]:
    _get_account_or_404(db, account_id)
    return [
        GroupedTradeStatsResponse.model_validate(g)
        for g in get_pre_event_vs_post_confirmation_contribution(db, account_id=account_id)
    ]


@router.get("/strategy/{account_id}/score-band", response_model=list[GroupedTradeStatsResponse])
def get_score_band_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[GroupedTradeStatsResponse]:
    _get_account_or_404(db, account_id)
    return [
        GroupedTradeStatsResponse.model_validate(g)
        for g in get_results_by_score_band(db, account_id=account_id)
    ]


@router.get("/strategy/{account_id}/sector", response_model=list[GroupedTradeStatsResponse])
def get_sector_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[GroupedTradeStatsResponse]:
    _get_account_or_404(db, account_id)
    return [
        GroupedTradeStatsResponse.model_validate(g)
        for g in get_results_by_sector(db, account_id=account_id)
    ]


@router.get("/strategy/{account_id}/policy-vetoes", response_model=PolicyVetoOutcomesResponse)
def get_policy_veto_outcomes_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> PolicyVetoOutcomesResponse:
    _get_account_or_404(db, account_id)
    return PolicyVetoOutcomesResponse.model_validate(
        get_policy_veto_outcomes(db, account_id=account_id)
    )


@router.get("/recommendations/reality", response_model=list[RecommendationRealityRowResponse])
def get_recommendation_reality_view(
    db: Session = Depends(get_db),
) -> list[RecommendationRealityRowResponse]:
    return [
        RecommendationRealityRowResponse.model_validate(r)
        for r in get_recommendation_reality_rows(db)
    ]


@router.get("/morning-plan/quality", response_model=MorningPlanQualitySummaryResponse)
def get_morning_plan_quality_view(
    db: Session = Depends(get_db), since: date | None = Query(default=None)
) -> MorningPlanQualitySummaryResponse:
    return MorningPlanQualitySummaryResponse.model_validate(
        get_morning_plan_quality_summary(db, since=since)
    )


@router.get("/morning-plan/sections", response_model=list[SectionResultsResponse])
def get_morning_plan_sections_view(
    db: Session = Depends(get_db),
) -> list[SectionResultsResponse]:
    return [SectionResultsResponse.model_validate(r) for r in get_realized_results_by_section(db)]


@router.get("/morning-plan/approval-conversion", response_model=ApprovalConversionResponse)
def get_approval_conversion_view(db: Session = Depends(get_db)) -> ApprovalConversionResponse:
    return ApprovalConversionResponse.model_validate(get_approval_conversion(db))


@router.get("/coach/{account_id}", response_model=CoachSummaryResult)
def get_coach_summary_view(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> CoachSummaryResult:
    """"The AI coach may summarize behavior only when the sample is
    adequate and must display sample size and uncertainty" (Revision
    Prompt 12). Sample adequacy is decided by `get_coach_summary()`
    itself, deterministically, before any LLM call. `LLMProvider` is
    deliberately NOT a FastAPI `Depends` here: resolving it eagerly would
    503 this endpoint whenever `ANTHROPIC_API_KEY` is absent, even for
    the (common) inadequate-sample case that never needs an LLM at all —
    it is only constructed once the sample is already known to be
    adequate."""
    account = _get_account_or_404(db, account_id)
    performance = get_portfolio_performance(db, account=account, as_of=datetime.now(UTC).date())
    is_adequate = performance.trade_stats.num_trades >= MIN_SAMPLE_SIZE_FOR_SUMMARY
    llm = get_llm_provider() if is_adequate else None
    return get_coach_summary(performance=performance, llm=llm)


# ------------------------------------------------------------------
# Charts (Revision Prompt 12's own required chart list)
# ------------------------------------------------------------------


@router.get("/charts/equity-curve/{account_id}", response_model=EquityCurveChartResponse)
def get_equity_curve_chart(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=1, le=730),
) -> EquityCurveChartResponse:
    account = _get_account_or_404(db, account_id)
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    account_points = get_equity_curve(db, account=account, start=start, end=end)

    spy = db.scalar(select(Instrument).where(Instrument.ticker == _SPY_TICKER))
    benchmark_points: list[EquityPointResponse] = []
    if spy is not None:
        bars = db.scalars(
            select(MarketBar)
            .where(
                MarketBar.instrument_id == spy.id,
                MarketBar.timeframe == Timeframe.DAILY,
                MarketBar.as_of >= start,
                MarketBar.as_of <= end,
            )
            .order_by(MarketBar.as_of.asc())
        ).all()
        # Rebased to the account's starting equity so the two series are
        # visually comparable on one chart, never presented as the same
        # dollar amount invested.
        starting_equity = account_points[0].equity if account_points else account.starting_cash
        first_close = bars[0].close if bars else None
        for bar in bars:
            if first_close is None or first_close == 0:
                continue
            rebased = starting_equity * (bar.close / first_close)
            benchmark_points.append(
                EquityPointResponse(
                    as_of=bar.as_of, cash=Decimal(0), market_value=rebased, equity=rebased
                )
            )

    return EquityCurveChartResponse(
        account_points=[EquityPointResponse.model_validate(p) for p in account_points],
        benchmark_points=benchmark_points,
    )


@router.get("/charts/drawdown/{account_id}", response_model=list[DrawdownChartPoint])
def get_drawdown_chart(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=1, le=730),
) -> list[DrawdownChartPoint]:
    account = _get_account_or_404(db, account_id)
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    points = get_equity_curve(db, account=account, start=start, end=end)
    if not points:
        return []
    equities = [p.equity for p in points]
    peak = equities[0]
    chart: list[DrawdownChartPoint] = []
    for point in points:
        peak = max(peak, point.equity)
        dd = (point.equity - peak) / peak * Decimal(100) if peak != 0 else Decimal(0)
        chart.append(DrawdownChartPoint(as_of=point.as_of, drawdown_pct=dd))
    return chart


@router.get(
    "/charts/score-threshold-sensitivity/{account_id}",
    response_model=list[ScoreThresholdSensitivityPoint],
)
def get_score_threshold_sensitivity_chart(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[ScoreThresholdSensitivityPoint]:
    """VALIDATION's "test score thresholds 4 through 7" against this
    account's own realized trade history."""
    _get_account_or_404(db, account_id)
    results = get_score_threshold_sensitivity(db, account_id=account_id, thresholds=[4, 5, 6, 7])
    return [
        ScoreThresholdSensitivityPoint(
            score_threshold=int(g.group_key.removeprefix(">=")),
            stats=TradeStatsResponse.model_validate(g.stats),
        )
        for g in results
    ]


@router.get("/charts/expected-vs-realized-move", response_model=list[dict[str, Decimal]])
def get_expected_vs_realized_move_chart(db: Session = Depends(get_db)) -> list[dict[str, Decimal]]:
    """Every earnings event with both a pre-event expected-move snapshot
    and a recorded historical gap — the calibration input for "was the
    expected move actually a good estimate.\""""
    rows = db.execute(
        select(
            EventExpectedMoveSnapshot.selected_expected_move_pct, EarningsHistoricalGap.gap_pct
        ).join(
            EarningsHistoricalGap,
            EarningsHistoricalGap.earnings_event_id == EventExpectedMoveSnapshot.earnings_event_id,
        )
    ).all()
    return [
        {"expected_move_pct": expected, "realized_move_pct": abs(gap)} for expected, gap in rows
    ]


@router.get("/charts/calibration", response_model=dict[str, dict[str, Decimal | int]])
def get_calibration_chart(db: Session = Depends(get_db)) -> dict[str, dict[str, Decimal | int]]:
    """Confidence-band hit rate — the live-computed equivalent of the
    (currently seed-only) `ConfidenceCalibrationRecord` concept: for
    each `RecommendationConfidence` band, the share of that band's
    recommendations whose linked outcome was a realized win. A band with
    zero sample reports `sample_size: 0` and no `hit_rate_pct` key at
    all, never a fabricated rate."""
    result: dict[str, dict[str, Decimal | int]] = {}
    for band in RecommendationConfidence:
        version_ids = db.scalars(
            select(RecommendationVersion.id).where(RecommendationVersion.confidence == band)
        ).all()
        if not version_ids:
            result[band.value] = {"sample_size": 0}
            continue

        pnls = db.scalars(
            select(Trade.realized_pnl)
            .join(RecommendationAttribution, RecommendationAttribution.trade_id == Trade.id)
            .where(
                RecommendationAttribution.recommendation_version_id.in_(version_ids),
                Trade.status == TradeStatus.CLOSED,
                Trade.realized_pnl.is_not(None),
            )
        ).all()
        closed_pnls = [p for p in pnls if p is not None]
        if not closed_pnls:
            result[band.value] = {"sample_size": 0}
            continue
        wins = sum(1 for p in closed_pnls if p > 0)
        result[band.value] = {
            "sample_size": len(closed_pnls),
            "hit_rate_pct": Decimal(wins) / Decimal(len(closed_pnls)) * Decimal(100),
        }
    return result


@router.get(
    "/charts/morning-recommendation-funnel", response_model=MorningRecommendationFunnelResponse
)
def get_morning_recommendation_funnel_chart(
    db: Session = Depends(get_db),
) -> MorningRecommendationFunnelResponse:
    plans_count = len(db.scalars(select(MorningPlanRun.id)).all())
    items = db.scalars(select(MorningPlanItem)).all()
    action_items = [i for i in items if i.action_label is not None]
    approvals = db.scalars(select(OrderApproval)).all()
    approved = [a for a in approvals if a.status == OrderApprovalStatus.APPROVED]
    submitted = (
        db.scalars(
            select(BrokerSubmissionAttempt.id).where(
                BrokerSubmissionAttempt.outcome == BrokerSubmissionOutcome.SUCCEEDED
            )
        ).all()
        if approved
        else []
    )
    return MorningRecommendationFunnelResponse(
        plans_generated=plans_count,
        items_surfaced=len(items),
        action_items=len(action_items),
        approvals_requested=len(approvals),
        approvals_granted=len(approved),
        orders_submitted=len(submitted),
    )
