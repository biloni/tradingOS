"""Validation grid, baseline reproduction, and go/no-go reporting
(Revision Prompt 13). Every function here composes `run_backtest()`
(`services/backtest_engine.py`) — no validation logic re-implements the
simulation itself, only orchestrates many runs and summarizes them.

**Baseline reproduction — read this before trusting any number below.**
Prompt 13's locked regression scenario (2026-02-03 to 2026-07-31, score
>= 5, expected move >= 4%) targets ~25 scored trades, ~+3.32% return,
~-1.67% max drawdown, ~48% win rate, ~1.67 profit factor. None of these
numbers appear anywhere in this codebase's own docs (confirmed by
targeted search before this revision began) — they are external targets
from a spec this project has no access to. Running the exact scenario
against this module's synthetic 20-instrument universe
(`services/backtest_data.py`) over that exact 6-month window produces
only ~7 trades — nowhere near enough to compare meaningfully against a
~25-trade target, and this module does not pretend otherwise. Widening
to the full 2-year synthetic window (~29 trades) is reported alongside
it as the more statistically meaningful run, per Prompt 13's own
instruction: "do not force these results... explain every deviation."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import EventBacktestDatasetSplit, EventBacktestStrategyKey
from tradingos_api.services.backtest_engine import BacktestResult, BacktestRunConfig, run_backtest
from tradingos_api.services.performance_metrics import (
    DrawdownResult,
    TradeStatsResult,
    compute_trade_stats,
)

CALCULATION_VERSION = "v1"

LOCKED_SCENARIO_START = date(2026, 2, 3)
LOCKED_SCENARIO_END = date(2026, 7, 31)
WIDE_UNIVERSE_START = date(2024, 8, 1)
WIDE_UNIVERSE_END = date(2026, 7, 31)

BASELINE_TARGETS: dict[str, Decimal | int] = {
    "num_trades": 25,
    "total_return_pct": Decimal("3.32"),
    "max_drawdown_pct": Decimal("-1.67"),
    "win_rate_pct": Decimal("48"),
    "profit_factor": Decimal("1.67"),
}
"""Prompt 13's own stated targets — a constant for comparison display
only, never a value this module tries to force a run to match."""

SEMICONDUCTOR_TICKERS: tuple[str, ...] = (
    "AMD", "TSM", "AVGO", "SNDK", "ADI", "NXPI", "ON", "ARM", "MRVL", "ALAB",
)  # fmt: skip


def _locked_baseline_config(*, start: date, end: date) -> BacktestRunConfig:
    return BacktestRunConfig(
        strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
        initial_equity=Decimal(10000),
        start=start,
        end=end,
        universe_start=WIDE_UNIVERSE_START,
        universe_end=WIDE_UNIVERSE_END,
        score_threshold=5,
        expected_move_threshold_pct=Decimal(4),
        normal_risk_pct=Decimal("0.50"),
        speculative_risk_pct=Decimal("0.25"),
        max_position_pct=Decimal("15.00"),
        max_sector_pct=Decimal("25.00"),
        max_concurrent_positions=3,
        fee_bps=Decimal(5),
    )


@dataclass(frozen=True)
class BaselineReproductionReport:
    locked_window_result: BacktestResult
    """The exact locked scenario window (2026-02-03 to 2026-07-31) —
    reported for completeness even though its trade count is too small
    to compare meaningfully against the target."""
    wide_window_result: BacktestResult
    """The same strategy/parameters over the full 2-year synthetic
    window — the run this module actually treats as informative."""
    targets: dict[str, Decimal | int]
    deviation_explanation: str
    calculation_version: str = CALCULATION_VERSION


def reproduce_baseline_scenario(db: Session) -> BaselineReproductionReport:
    locked_config = _locked_baseline_config(start=LOCKED_SCENARIO_START, end=LOCKED_SCENARIO_END)
    wide_config = _locked_baseline_config(start=WIDE_UNIVERSE_START, end=WIDE_UNIVERSE_END)
    locked_result = run_backtest(db, locked_config)
    wide_result = run_backtest(db, wide_config)
    explanation = (
        f"This dev environment's real MarketBar/EarningsEvent history covers ~3 months "
        f"across 6 instruments with only 3 real earnings events total — nowhere near "
        f"enough to run the locked scenario's 2026-02-03 to 2026-07-31 window or produce "
        f"~25 scored trades. A deterministic synthetic universe (20 instruments, 2 years, "
        f"seed={locked_config.seed}) was generated instead. Run against the exact locked "
        f"window, it produces {len(locked_result.trades)} trades — too sparse to compare "
        f"meaningfully against a 25-trade target. Widened to the full 2-year synthetic "
        f"window, the same strategy/parameters produce {len(wide_result.trades)} trades. "
        f"Neither run's outcome should be read as validating or invalidating the live "
        f"strategy's real-world edge: the synthetic price/earnings-gap generator "
        f"(services/backtest_data.py) injects no relationship between the score and the "
        f"subsequent gap direction, so this comparison exercises the engine's mechanics "
        f"(fills, sizing, caps, fees, no-look-ahead) honestly, not the strategy's true "
        f"predictive value."
    )
    return BaselineReproductionReport(
        locked_window_result=locked_result,
        wide_window_result=wide_result,
        targets=BASELINE_TARGETS,
        deviation_explanation=explanation,
    )


@dataclass(frozen=True)
class SweepPoint:
    label: str
    result: BacktestResult


def run_score_threshold_sweep(
    db: Session, *, thresholds: tuple[int, ...] = (4, 5, 6, 7)
) -> list[SweepPoint]:
    points: list[SweepPoint] = []
    for threshold in thresholds:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            start=WIDE_UNIVERSE_START,
            end=WIDE_UNIVERSE_END,
            universe_start=WIDE_UNIVERSE_START,
            universe_end=WIDE_UNIVERSE_END,
            score_threshold=threshold,
        )
        points.append(SweepPoint(f">={threshold}", run_backtest(db, config)))
    return points


def run_expected_move_threshold_sweep(
    db: Session, *, thresholds: tuple[int, ...] = (3, 4, 5, 6)
) -> list[SweepPoint]:
    points: list[SweepPoint] = []
    for threshold in thresholds:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            start=WIDE_UNIVERSE_START,
            end=WIDE_UNIVERSE_END,
            universe_start=WIDE_UNIVERSE_START,
            universe_end=WIDE_UNIVERSE_END,
            expected_move_threshold_pct=Decimal(threshold),
        )
        points.append(SweepPoint(f">={threshold}%", run_backtest(db, config)))
    return points


def run_risk_budget_sweep(
    db: Session, *, budgets: tuple[Decimal, ...] = (Decimal("0.25"), Decimal("0.50"))
) -> list[SweepPoint]:
    points: list[SweepPoint] = []
    for budget in budgets:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            start=WIDE_UNIVERSE_START,
            end=WIDE_UNIVERSE_END,
            universe_start=WIDE_UNIVERSE_START,
            universe_end=WIDE_UNIVERSE_END,
            normal_risk_pct=budget,
        )
        points.append(SweepPoint(f"{budget}%", run_backtest(db, config)))
    return points


def run_lane_variant_comparison(db: Session) -> list[SweepPoint]:
    """Pre-event-only (the baseline itself, which never adds a post-
    confirmation leg), post-confirmation-only, and hybrid — Prompt 13's
    explicit "test pre-event-only/post-confirmation-only/hybrid"
    requirement."""
    keys = [
        ("PRE_EVENT_ONLY", EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE),
        ("POST_CONFIRMATION_ONLY", EventBacktestStrategyKey.POST_CONFIRMATION_ONLY),
        ("HYBRID", EventBacktestStrategyKey.HYBRID_PRE_AND_POST),
    ]
    points: list[SweepPoint] = []
    for label, key in keys:
        config = BacktestRunConfig(
            strategy_key=key,
            start=WIDE_UNIVERSE_START,
            end=WIDE_UNIVERSE_END,
            universe_start=WIDE_UNIVERSE_START,
            universe_end=WIDE_UNIVERSE_END,
        )
        points.append(SweepPoint(label, run_backtest(db, config)))
    return points


def run_semiconductor_concentration_subset(db: Session) -> BacktestResult:
    """"Test semiconductor concentration" — the baseline strategy run
    against a universe restricted to the 10 semiconductor names only, so
    the sector cap (25%) and position cap (15%) become the binding
    constraints rather than diversification across sectors."""
    config = BacktestRunConfig(
        strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
        start=WIDE_UNIVERSE_START,
        end=WIDE_UNIVERSE_END,
        universe_start=WIDE_UNIVERSE_START,
        universe_end=WIDE_UNIVERSE_END,
        universe_tickers=SEMICONDUCTOR_TICKERS,
    )
    return run_backtest(db, config)


@dataclass(frozen=True)
class WalkForwardWindow:
    split: EventBacktestDatasetSplit
    label: str
    start: date
    end: date
    result: BacktestResult


def run_walk_forward(db: Session) -> list[WalkForwardWindow]:
    """Three non-overlapping windows over the full 2-year synthetic
    universe — TRAIN (first 12 months), VALIDATION (next 6 months),
    OUT_OF_SAMPLE (final 6 months). No parameter re-optimization happens
    between windows (docs/DECISIONS.md's Prompt 13 ADR is explicit that
    this is walk-forward *evaluation* of one fixed rule, not a re-fit
    loop) — the same locked baseline config runs unchanged in each
    window, and results are reported side by side."""
    windows = [
        (EventBacktestDatasetSplit.TRAIN, "TRAIN", date(2024, 8, 1), date(2025, 7, 31)),
        (
            EventBacktestDatasetSplit.VALIDATION,
            "VALIDATION",
            date(2025, 8, 1),
            date(2026, 1, 31),
        ),
        (
            EventBacktestDatasetSplit.OUT_OF_SAMPLE,
            "OUT_OF_SAMPLE",
            date(2026, 2, 1),
            date(2026, 7, 31),
        ),
    ]
    results: list[WalkForwardWindow] = []
    for split, label, start, end in windows:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            start=start,
            end=end,
            universe_start=WIDE_UNIVERSE_START,
            universe_end=WIDE_UNIVERSE_END,
        )
        results.append(WalkForwardWindow(split, label, start, end, run_backtest(db, config)))
    return results


def results_by_year(result: BacktestResult) -> list[SweepPoint]:
    years = sorted({t.entry_date.year for t in result.trades})
    points: list[SweepPoint] = []
    for year in years:
        pnls = [t.pnl_usd for t in result.trades if t.entry_date.year == year]
        stats = compute_trade_stats(pnls)
        points.append(SweepPoint(str(year), _stats_only_result(result, stats)))
    return points


def results_by_sector(result: BacktestResult) -> list[SweepPoint]:
    sectors = sorted({t.sector for t in result.trades if t.sector is not None})
    points: list[SweepPoint] = []
    for sector in sectors:
        pnls = [t.pnl_usd for t in result.trades if t.sector == sector]
        stats = compute_trade_stats(pnls)
        points.append(SweepPoint(sector, _stats_only_result(result, stats)))
    return points


def _stats_only_result(source: BacktestResult, stats: TradeStatsResult) -> BacktestResult:
    """A `BacktestResult`-shaped wrapper carrying only `trade_stats` for
    a filtered sub-group — the other fields are copied from the source
    run (same config/equity curve context) so `SweepPoint` can reuse one
    response shape across full-run and per-group results without a
    second, narrower schema."""
    return BacktestResult(
        config=source.config,
        trades=[],
        equity_curve=[],
        trade_stats=stats,
        annualized_volatility_pct=None,
        sharpe_ratio=None,
        sortino_ratio=None,
        drawdown=DrawdownResult(Decimal(0), None, None, None, None),
        total_return_pct=None,
        benchmark_return_pct=None,
        events_seen=0,
        events_eligible=0,
    )


@dataclass(frozen=True)
class GoNoGoReport:
    baseline: BaselineReproductionReport
    strategy_comparison: list[SweepPoint]
    score_threshold_sensitivity: list[SweepPoint]
    expected_move_threshold_sensitivity: list[SweepPoint]
    risk_budget_sensitivity: list[SweepPoint]
    lane_variant_comparison: list[SweepPoint]
    semiconductor_concentration: BacktestResult
    walk_forward: list[WalkForwardWindow]
    by_year: list[SweepPoint]
    by_sector: list[SweepPoint]
    bias_and_quality_caveats: list[str]
    recommendation: str
    calculation_version: str = CALCULATION_VERSION


_BIAS_CAVEATS = [
    "Synthetic price/earnings history (services/backtest_data.py), not real market "
    "data — real MarketBar/EarningsEvent coverage in this dev environment is ~3 months "
    "across 6 instruments with 3 total earnings events, far short of what this "
    "validation requires.",
    "The synthetic earnings-gap generator injects no relationship between the score's "
    "components and the subsequent price gap — results below reflect the engine's "
    "mechanics (fills, sizing, caps, fees) honestly, not a real predictive edge.",
    "20-instrument universe, hand-selected from this project's own seeded Instrument "
    "rows (semiconductor-heavy) — not a broad-market universe, and not free of "
    "selection bias since the same 20 names are reused across every strategy variant.",
    "No survivorship-bias model: every selected ticker exists for the entire "
    "generated window by construction (this synthetic universe has no delisting "
    "concept), the same accepted limitation the retired backtest engine's own "
    "ADR-025 already documents for a fixed-watchlist system.",
    "No bid/ask spread, partial fills, or rejected-entry modeling beyond a flat "
    "5bps-per-fill fee and stop-before-target ambiguity resolution — a real broker "
    "would sometimes fill worse than the modeled next-bar open, especially on a gap.",
    "Walk-forward here means evaluating one fixed rule across three non-overlapping "
    "windows, never re-optimizing between them — this validates temporal stability "
    "of a fixed rule, not a re-fit strategy's robustness.",
]


def build_go_no_go_report(db: Session) -> GoNoGoReport:
    baseline = reproduce_baseline_scenario(db)
    strategy_comparison = [
        SweepPoint(
            key.value,
            run_backtest(
                db,
                BacktestRunConfig(
                    strategy_key=key, start=WIDE_UNIVERSE_START, end=WIDE_UNIVERSE_END,
                    universe_start=WIDE_UNIVERSE_START, universe_end=WIDE_UNIVERSE_END,
                ),
            ),
        )
        for key in EventBacktestStrategyKey
    ]  # fmt: skip
    wide_baseline = baseline.wide_window_result

    num_trades = len(wide_baseline.trades)
    win_rate = wide_baseline.trade_stats.win_rate_pct
    sharpe = wide_baseline.sharpe_ratio
    if num_trades < 30:
        recommendation = (
            f"REJECT for paper activation as evidence, PENDING MORE DATA. "
            f"Only {num_trades} independent trades were produced even over the widened "
            f"2-year synthetic window — below any reasonable minimum sample size for a "
            f"go-live decision, and the underlying data is synthetic with no embedded "
            f"predictive signal by construction. This report validates the backtest "
            f"engine's mechanics (no-look-ahead, correct sizing/caps/fees, working exit "
            f"logic across all 8 strategies) — it does not and cannot validate the live "
            f"strategy's real-world edge. Re-run against real multi-year point-in-time "
            f"market/earnings data before this becomes a paper-activation decision."
        )
    elif sharpe is not None and sharpe > 0 and win_rate is not None and win_rate >= Decimal(40):
        recommendation = (
            "MODIFY: promising mechanics, insufficient real-data sample — "
            "re-validate before paper activation."
        )
    else:
        recommendation = "REJECT for paper activation in its current form — see caveats."

    return GoNoGoReport(
        baseline=baseline,
        strategy_comparison=strategy_comparison,
        score_threshold_sensitivity=run_score_threshold_sweep(db),
        expected_move_threshold_sensitivity=run_expected_move_threshold_sweep(db),
        risk_budget_sensitivity=run_risk_budget_sweep(db),
        lane_variant_comparison=run_lane_variant_comparison(db),
        semiconductor_concentration=run_semiconductor_concentration_subset(db),
        walk_forward=run_walk_forward(db),
        by_year=results_by_year(wide_baseline),
        by_sector=results_by_sector(wide_baseline),
        bias_and_quality_caveats=_BIAS_CAVEATS,
        recommendation=recommendation,
    )


__all__ = [
    "BASELINE_TARGETS",
    "BaselineReproductionReport",
    "GoNoGoReport",
    "SweepPoint",
    "WalkForwardWindow",
    "build_go_no_go_report",
    "reproduce_baseline_scenario",
    "run_expected_move_threshold_sweep",
    "run_lane_variant_comparison",
    "run_risk_budget_sweep",
    "run_score_threshold_sweep",
    "run_semiconductor_concentration_subset",
    "run_walk_forward",
]
