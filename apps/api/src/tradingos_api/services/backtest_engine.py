"""Event-driven backtest engine (Revision Prompt 13). Reuses "the exact
live strategy versions" wherever a pure, DB-free live function already
computes the signal in question, rather than re-deriving a second
implementation for backtesting:

- `services/earnings_score.py::compute_tactical_earnings_score()` — the
  live 8-component direction score, unmodified.
- `services/expected_move.py::compute_expected_move()` — the live
  `max(ATR%, historical_median_gap%)` selection, unmodified.
- `services/position_sizing.py::compute_tactical_position_size()` — the
  live risk-budget-÷-expected-move sizing with its six sequential caps,
  unmodified.
- `services/recommendation_reality.py::compute_hypothetical_outcome()` —
  Revision Prompt 12's next-bar-fill, stop-before-target-on-ambiguity
  exit walk, reused here for every strategy's exit simulation (the
  single place "how does a simulated position actually close" is
  answered, for both the live recommendation-reality feature and this
  revision's backtester — see docs/DECISIONS.md's Prompt 13 ADR).
- `services/performance_metrics.py` — every aggregate statistic
  (Sharpe/Sortino/drawdown/trade-stats), the same DB-free library
  Revision Prompt 12's live-portfolio dashboard uses (ADR-062's own
  stated intent, realized here).

**One deliberate deviation from the live gate**:
`services/baseline_eligibility.py::evaluate_baseline_eligibility()`
hardcodes `_MIN_DIRECTION_SCORE = 6` — a fixed, shipped policy value.
Revision Prompt 13 explicitly asks to *test* score thresholds 4-7 as a
research parameter, which is incompatible with a hardcoded live gate by
definition. `_passes_eligibility_gate()` below re-expresses the same
four numeric conditions (score, expected move, liquidity, analyst
coverage) with the threshold as a config field — the two non-numeric
live conditions (verified timing, fresh evidence, portfolio/sector
capacity, no unresolved data-quality issue) either don't apply to a
backtest (there is no "stale evidence" in a fully-known historical
series) or are enforced by the portfolio allocator itself (capacity),
not by this gate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    EventBacktestExitReason,
    EventBacktestStrategyKey,
    EventBacktestTradeLane,
)
from tradingos_api.services.analytics import atr, ema, liquidity
from tradingos_api.services.backtest_data import (
    DEFAULT_SEED,
    DEFAULT_UNIVERSE_TICKERS,
    SyntheticEarningsEvent,
    SyntheticInstrumentSeries,
    SyntheticUniverse,
    generate_synthetic_universe,
)
from tradingos_api.services.earnings_score import compute_tactical_earnings_score
from tradingos_api.services.expected_move import compute_expected_move
from tradingos_api.services.market_regime import classify_market_regime
from tradingos_api.services.performance_metrics import (
    CALCULATION_VERSION as METRICS_CALCULATION_VERSION,
)
from tradingos_api.services.performance_metrics import (
    DrawdownResult,
    TradeStatsResult,
    annualized_volatility,
    compute_trade_stats,
    daily_returns_from_equity_curve,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)
from tradingos_api.services.position_sizing import (
    DEFAULT_SLIPPAGE_BPS,
    compute_tactical_position_size,
)
from tradingos_api.services.recommendation_reality import compute_hypothetical_outcome

CALCULATION_VERSION = "v1"

DEFAULT_MAX_LIQUIDITY_PCT_OF_ADV = Decimal("8.00")
DEFAULT_SPECULATIVE_POSITION_CAP_PCT = Decimal("7.50")
DEFAULT_MIN_AVG_DAILY_DOLLAR_VOLUME = Decimal("50000000")
DEFAULT_MIN_ANALYST_ESTIMATES = 3
TARGET_MULTIPLE_OF_EXPECTED_MOVE = Decimal(2)
"""Documented modeling assumption: the live system's real stop/target
composite (docs/DECISIONS.md ADR-035 — ATR + structure + gap + catalyst
+ trailing) requires a support/resistance pivot detector this revision
does not build. This backtest instead sizes both the stop and the target
directly off the same `selected_expected_move_pct` the position-sizing
formula already uses (stop = 1x expected move, target = 2x expected
move) — internally consistent with "the position is sized so that a
move equal to the expected move costs exactly the risk budget," but a
real, named simplification versus the live composite rule."""


@dataclass(frozen=True)
class BacktestRunConfig:
    """Every field is versioned/snapshotted onto `EventBacktestRun.config`
    for reproducibility (principle 8/9) — a run is fully determined by
    `(strategy_key, seed, start, end, universe_tickers)` plus these
    parameters, nothing else."""

    strategy_key: EventBacktestStrategyKey
    initial_equity: Decimal = Decimal(10000)
    start: date = date(2024, 8, 1)
    """Start of the *trading-eligible* window — an event/signal outside
    `[start, end]` is never traded, even though it may still be visible
    to indicators as history. Defaults equal to `universe_start` (trade
    across everything generated); the locked baseline scenario overrides
    this to a narrower 6-month window while `universe_start` stays wide
    enough for indicator warm-up."""
    end: date = date(2026, 7, 31)
    universe_start: date = date(2024, 8, 1)
    """Start of the *generated* price/earnings history — always wide
    enough to give every indicator (EMA50, ATR14, momentum) its required
    lookback before `start`, so narrowing the tradeable window never
    starves an indicator of history it would otherwise have had."""
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
    min_analyst_estimates: int = DEFAULT_MIN_ANALYST_ESTIMATES
    min_avg_daily_dollar_volume: Decimal = DEFAULT_MIN_AVG_DAILY_DOLLAR_VOLUME
    max_liquidity_pct_of_adv: Decimal = DEFAULT_MAX_LIQUIDITY_PCT_OF_ADV
    speculative_position_pct_cap: Decimal = DEFAULT_SPECULATIVE_POSITION_CAP_PCT
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS
    seed: int = DEFAULT_SEED
    universe_tickers: tuple[str, ...] = DEFAULT_UNIVERSE_TICKERS


@dataclass(frozen=True)
class SimulatedTrade:
    instrument_id: uuid.UUID
    ticker: str
    sector: str | None
    lane: EventBacktestTradeLane
    event_date: date | None
    fiscal_period: str | None
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    quantity: int
    fees_usd: Decimal
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: EventBacktestExitReason
    score: Decimal | None
    expected_move_pct: Decimal | None


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestRunConfig
    trades: list[SimulatedTrade]
    equity_curve: list[tuple[date, Decimal]]
    trade_stats: TradeStatsResult
    annualized_volatility_pct: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    drawdown: DrawdownResult
    total_return_pct: Decimal | None
    benchmark_return_pct: Decimal | None
    events_seen: int
    events_eligible: int
    calculation_version: str = CALCULATION_VERSION


@dataclass(frozen=True)
class _Opportunity:
    instrument_id: uuid.UUID
    ticker: str
    sector: str | None
    lane: EventBacktestTradeLane
    event_date: date | None
    fiscal_period: str | None
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    exit_reason: EventBacktestExitReason
    score: Decimal | None
    expected_move_pct: Decimal | None
    avg_daily_dollar_volume: Decimal | None
    risk_pct: Decimal


@dataclass
class _OpenPosition:
    sector: str | None
    exit_date: date
    entry_notional: Decimal
    exit_notional: Decimal
    exit_fee: Decimal


def _bar_index_by_date(series: SyntheticInstrumentSeries) -> dict[date, int]:
    return {b.as_of: i for i, b in enumerate(series.bars)}


def _passes_eligibility_gate(
    *,
    score_total: int,
    score_threshold: int,
    expected_move_pct: Decimal | None,
    move_threshold_pct: Decimal,
    avg_daily_dollar_volume: Decimal | None,
    min_avg_daily_dollar_volume: Decimal,
    num_analysts: int,
    min_analysts: int,
) -> bool:
    return (
        score_total >= score_threshold
        and expected_move_pct is not None
        and expected_move_pct >= move_threshold_pct
        and avg_daily_dollar_volume is not None
        and avg_daily_dollar_volume >= min_avg_daily_dollar_volume
        and num_analysts >= min_analysts
    )


def _simulate_exit(
    *,
    series: SyntheticInstrumentSeries,
    reaction_idx: int,
    opened_at: date,
    entry_price: Decimal,
    stop_price: Decimal,
    target_price: Decimal,
    config: BacktestRunConfig,
) -> tuple[date, Decimal, EventBacktestExitReason] | None:
    """Reuses `compute_hypothetical_outcome()` verbatim — `entry_price`
    is set to the reaction bar's own open, and that bar's low is always
    <= its own open by construction, so `entry_window_days=3` always
    resolves the entry on the reaction bar itself; only the exit walk
    (stop/target/time-exit/end-of-history) is doing real work here."""
    if reaction_idx >= len(series.bars):
        return None
    bars = [(b.as_of, b.low, b.high, b.close) for b in series.bars[reaction_idx:]]
    outcome = compute_hypothetical_outcome(
        entry_price=entry_price,
        stop_price=stop_price,
        target_prices=[target_price],
        opened_at=opened_at,
        bars=bars,
        max_holding_days=config.max_holding_days,
        entry_window_days=config.entry_window_days,
    )
    if not outcome.entry_reachable or outcome.simulated_exit_price is None:
        return None
    assert outcome.simulated_exit_date is not None
    reason_map = {
        "STOP": EventBacktestExitReason.STOP,
        "TARGET": EventBacktestExitReason.TARGET,
        "TIME_EXIT": EventBacktestExitReason.TIME_EXIT,
        "END_OF_HISTORY": EventBacktestExitReason.END_OF_HISTORY,
    }
    reason = reason_map.get(
        outcome.simulated_exit_reason or "", EventBacktestExitReason.END_OF_HISTORY
    )
    return outcome.simulated_exit_date, outcome.simulated_exit_price, reason


def _evaluate_earnings_event(
    *,
    series: SyntheticInstrumentSeries,
    event_idx: int,
    universe: SyntheticUniverse,
    config: BacktestRunConfig,
) -> tuple[int, Decimal | None, Decimal | None, int] | None:
    """Point-in-time score/expected-move/liquidity for one earnings
    event — every input is sliced strictly through the report date's own
    close, and `prior_gap_pcts` only ever includes STRICTLY EARLIER
    events (no look-ahead into this event's own outcome or any future
    one)."""
    bar_index = _bar_index_by_date(series)
    event = series.earnings_events[event_idx]
    report_idx = bar_index.get(event.report_date)
    if report_idx is None or report_idx + 1 >= len(series.bars):
        return None

    closes: list[Decimal | None] = [b.close for b in series.bars[: report_idx + 1]]
    highs: list[Decimal | None] = [b.high for b in series.bars[: report_idx + 1]]
    lows: list[Decimal | None] = [b.low for b in series.bars[: report_idx + 1]]
    volumes: list[int | None] = [b.volume for b in series.bars[: report_idx + 1]]
    spy_closes: list[Decimal | None] = [b.close for b in universe.benchmark.bars[: report_idx + 1]]

    prior_gaps = [e.actual_gap_pct for e in series.earnings_events[:event_idx]][-3:]
    score_result = compute_tactical_earnings_score(
        instrument_closes=closes,
        spy_closes=spy_closes,
        instrument_volumes=volumes,
        consensus_eps_estimate=event.consensus_eps,
        prior_year_actual_eps=event.prior_year_actual_eps,
        num_analysts=event.num_analysts,
        prior_gap_pcts=prior_gaps,
        as_of=event.report_date,
    )

    atr_result = atr(highs, lows, closes, 14, event.report_date)
    last_close = closes[-1]
    atr_pct = None
    if atr_result.status == "OK" and atr_result.value is not None and last_close:
        atr_pct = (atr_result.value / last_close) * Decimal(100)
    prior_gaps_abs = [abs(g) for g in prior_gaps]
    move_result = compute_expected_move(
        atr_based_move_pct=atr_pct,
        prior_gap_abs_pcts=prior_gaps_abs,
        option_implied_move_pct=None,
        option_implied_available=False,
    )
    adv_result = liquidity(volumes, closes, 20, event.report_date)
    avg_dollar_volume = adv_result.value if adv_result.status == "OK" else None

    return (
        score_result.total_score,
        move_result.selected_expected_move_pct,
        avg_dollar_volume,
        event.num_analysts,
    )


def _build_pre_event_opportunity(
    *,
    series: SyntheticInstrumentSeries,
    event: SyntheticEarningsEvent,
    event_idx: int,
    score_total: int,
    expected_move_pct: Decimal,
    avg_dollar_volume: Decimal | None,
    lane: EventBacktestTradeLane,
    risk_pct: Decimal,
    config: BacktestRunConfig,
) -> _Opportunity | None:
    bar_index = _bar_index_by_date(series)
    report_idx = bar_index[event.report_date]
    reaction_idx = report_idx + 1
    entry_price = series.bars[reaction_idx].open
    stop_price = entry_price * (Decimal(1) - expected_move_pct / Decimal(100))
    target_price = entry_price * (
        Decimal(1) + (expected_move_pct * TARGET_MULTIPLE_OF_EXPECTED_MOVE) / Decimal(100)
    )
    exit_info = _simulate_exit(
        series=series,
        reaction_idx=reaction_idx,
        opened_at=series.bars[report_idx].as_of,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        config=config,
    )
    if exit_info is None:
        return None
    exit_date, exit_price, exit_reason = exit_info
    return _Opportunity(
        instrument_id=series.instrument_id,
        ticker=series.ticker,
        sector=series.sector,
        lane=lane,
        event_date=event.report_date,
        fiscal_period=event.fiscal_period,
        entry_date=series.bars[reaction_idx].as_of,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        score=Decimal(score_total),
        expected_move_pct=expected_move_pct,
        avg_daily_dollar_volume=avg_dollar_volume,
        risk_pct=risk_pct,
    )


def _build_post_confirmation_opportunity(
    *,
    series: SyntheticInstrumentSeries,
    event: SyntheticEarningsEvent,
    score_total: int,
    expected_move_pct: Decimal,
    avg_dollar_volume: Decimal | None,
    risk_pct: Decimal,
    config: BacktestRunConfig,
) -> _Opportunity | None:
    """Enters one trading day later than the pre-event leg — after the
    reaction gap is already known — and only when that reaction actually
    confirmed the score's implied bullish direction (`actual_gap_pct >
    0`), matching `docs/HYBRID_EARNINGS_STRATEGY.md`'s TRADE_ADD_CONFIRMED
    gate."""
    if event.actual_gap_pct <= 0:
        return None
    bar_index = _bar_index_by_date(series)
    report_idx = bar_index[event.report_date]
    confirmation_idx = report_idx + 2
    if confirmation_idx >= len(series.bars):
        return None
    entry_price = series.bars[confirmation_idx].open
    stop_price = entry_price * (Decimal(1) - expected_move_pct / Decimal(100))
    target_price = entry_price * (
        Decimal(1) + (expected_move_pct * TARGET_MULTIPLE_OF_EXPECTED_MOVE) / Decimal(100)
    )
    exit_info = _simulate_exit(
        series=series,
        reaction_idx=confirmation_idx,
        opened_at=series.bars[report_idx + 1].as_of,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        config=config,
    )
    if exit_info is None:
        return None
    exit_date, exit_price, exit_reason = exit_info
    return _Opportunity(
        instrument_id=series.instrument_id,
        ticker=series.ticker,
        sector=series.sector,
        lane=EventBacktestTradeLane.POST_CONFIRMATION,
        event_date=event.report_date,
        fiscal_period=event.fiscal_period,
        entry_date=series.bars[confirmation_idx].as_of,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=exit_reason,
        score=Decimal(score_total),
        expected_move_pct=expected_move_pct,
        avg_daily_dollar_volume=avg_dollar_volume,
        risk_pct=risk_pct,
    )


def _earnings_driven_opportunities(
    universe: SyntheticUniverse, config: BacktestRunConfig
) -> tuple[list[_Opportunity], int, int]:
    """Shared candidate generation for every earnings-driven strategy
    (baseline, conservative, hybrid, post-confirmation-only, control) —
    each strategy filters/shapes this same evaluated-event stream
    differently rather than re-walking the universe independently."""
    opportunities: list[_Opportunity] = []
    events_seen = 0
    events_eligible = 0
    score_threshold = (
        6
        if config.strategy_key == EventBacktestStrategyKey.CONSERVATIVE_SCORE_6
        else config.score_threshold
    )
    is_control = config.strategy_key == EventBacktestStrategyKey.TRADE_EVERY_EARNINGS_CONTROL
    is_post_only = config.strategy_key == EventBacktestStrategyKey.POST_CONFIRMATION_ONLY
    is_hybrid = config.strategy_key == EventBacktestStrategyKey.HYBRID_PRE_AND_POST

    for series in universe.instruments:
        for event_idx, event in enumerate(series.earnings_events):
            if not (config.start <= event.report_date <= config.end):
                continue
            evaluated = _evaluate_earnings_event(
                series=series, event_idx=event_idx, universe=universe, config=config
            )
            if evaluated is None:
                continue
            events_seen += 1
            score_total, expected_move_pct, avg_dollar_volume, num_analysts = evaluated
            if expected_move_pct is None:
                continue

            if is_control:
                eligible = (
                    avg_dollar_volume is not None
                    and avg_dollar_volume >= config.min_avg_daily_dollar_volume
                    and num_analysts >= config.min_analyst_estimates
                )
            else:
                eligible = _passes_eligibility_gate(
                    score_total=score_total,
                    score_threshold=score_threshold,
                    expected_move_pct=expected_move_pct,
                    move_threshold_pct=config.expected_move_threshold_pct,
                    avg_daily_dollar_volume=avg_dollar_volume,
                    min_avg_daily_dollar_volume=config.min_avg_daily_dollar_volume,
                    num_analysts=num_analysts,
                    min_analysts=config.min_analyst_estimates,
                )
            if not eligible:
                continue
            events_eligible += 1

            if is_post_only:
                opp = _build_post_confirmation_opportunity(
                    series=series,
                    event=event,
                    score_total=score_total,
                    expected_move_pct=expected_move_pct,
                    avg_dollar_volume=avg_dollar_volume,
                    risk_pct=config.normal_risk_pct,
                    config=config,
                )
                if opp is not None:
                    opportunities.append(opp)
                continue

            lane = (
                EventBacktestTradeLane.CONTROL if is_control else EventBacktestTradeLane.PRE_EVENT
            )
            pre_risk = config.speculative_risk_pct if is_hybrid else config.normal_risk_pct
            pre_opp = _build_pre_event_opportunity(
                series=series,
                event=event,
                event_idx=event_idx,
                score_total=score_total,
                expected_move_pct=expected_move_pct,
                avg_dollar_volume=avg_dollar_volume,
                lane=lane,
                risk_pct=pre_risk,
                config=config,
            )
            if pre_opp is not None:
                opportunities.append(pre_opp)

            if is_hybrid:
                post_opp = _build_post_confirmation_opportunity(
                    series=series,
                    event=event,
                    score_total=score_total,
                    expected_move_pct=expected_move_pct,
                    avg_dollar_volume=avg_dollar_volume,
                    risk_pct=config.normal_risk_pct,
                    config=config,
                )
                if post_opp is not None:
                    opportunities.append(post_opp)

    return opportunities, events_seen, events_eligible


def _ema_cross_opportunities(
    universe: SyntheticUniverse, config: BacktestRunConfig
) -> list[_Opportunity]:
    """The retired backtest engine's own original rule (ADR-023's
    threshold-crossing lineage), reused here as strategy #6's "original
    EMA-cross comparison" — a classic fast/slow EMA crossover, entirely
    independent of earnings events."""
    opportunities: list[_Opportunity] = []
    fast_window, slow_window = 12, 26
    for series in universe.instruments:
        closes: list[Decimal | None] = [b.close for b in series.bars]
        in_position_until_idx = -1
        for i in range(slow_window + 1, len(series.bars) - 1):
            if i <= in_position_until_idx:
                continue
            d = series.bars[i].as_of
            if not (config.start <= d <= config.end):
                continue
            fast_prev = ema(closes[:i], fast_window, d)
            slow_prev = ema(closes[:i], slow_window, d)
            fast_now = ema(closes[: i + 1], fast_window, d)
            slow_now = ema(closes[: i + 1], slow_window, d)
            indicators = (fast_prev, slow_prev, fast_now, slow_now)
            if any(r.status != "OK" or r.value is None for r in indicators):
                continue
            assert fast_prev.value is not None and slow_prev.value is not None
            assert fast_now.value is not None and slow_now.value is not None
            bullish_cross = fast_prev.value <= slow_prev.value and fast_now.value > slow_now.value
            if not bullish_cross:
                continue
            entry_idx = i + 1
            entry_price = series.bars[entry_idx].open
            stop_price = entry_price * Decimal("0.95")
            target_price = entry_price * Decimal("1.10")
            exit_info = _simulate_exit(
                series=series,
                reaction_idx=entry_idx,
                opened_at=d,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                config=config,
            )
            if exit_info is None:
                continue
            exit_date, exit_price, exit_reason = exit_info
            opportunities.append(
                _Opportunity(
                    instrument_id=series.instrument_id,
                    ticker=series.ticker,
                    sector=series.sector,
                    lane=EventBacktestTradeLane.CONTROL,
                    event_date=None,
                    fiscal_period=None,
                    entry_date=series.bars[entry_idx].as_of,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    score=None,
                    expected_move_pct=None,
                    avg_daily_dollar_volume=None,
                    risk_pct=config.normal_risk_pct,
                )
            )
            exit_idx = next(
                (j for j, b in enumerate(series.bars) if b.as_of == exit_date), len(series.bars)
            )
            in_position_until_idx = exit_idx
    return opportunities


def _regime_pullback_opportunities(
    universe: SyntheticUniverse, config: BacktestRunConfig
) -> list[_Opportunity]:
    """"Regime-pullback comparison" — reuses the live
    `services/market_regime.py::classify_market_regime()` (QQQ history
    substituted with SPY's own, since this synthetic universe has no
    separate QQQ/VIX-proxy series; the function degrades to its own
    documented conservative default, `ELEVATED`, when those inputs are
    unavailable, which is an accepted, honestly-labeled limitation, not
    a silent gap). Enters an instrument that has pulled back to within
    1.5% of its EMA20 while still above its EMA50, and the regime is not
    `STRESSED`."""
    opportunities: list[_Opportunity] = []
    spy_closes: list[Decimal | None] = [b.close for b in universe.benchmark.bars]
    for series in universe.instruments:
        closes: list[Decimal | None] = [b.close for b in series.bars]
        in_position_until_idx = -1
        for i in range(55, len(series.bars) - 1):
            if i <= in_position_until_idx:
                continue
            d = series.bars[i].as_of
            if not (config.start <= d <= config.end):
                continue
            ema20 = ema(closes[: i + 1], 20, d)
            ema50 = ema(closes[: i + 1], 50, d)
            if ema20.status != "OK" or ema50.status != "OK":
                continue
            assert ema20.value is not None and ema50.value is not None
            close_now = series.bars[i].close
            if close_now <= ema50.value:
                continue
            pct_from_ema20 = abs((close_now - ema20.value) / ema20.value) * Decimal(100)
            if pct_from_ema20 > Decimal("1.5"):
                continue
            regime = classify_market_regime(
                spy_closes=spy_closes[: i + 1],
                qqq_closes=spy_closes[: i + 1],
                vix_proxy_closes=[],
                breadth_pct_above_sma50=None,
                as_of=d,
            )
            if regime.classification == "STRESSED":
                continue
            entry_idx = i + 1
            entry_price = series.bars[entry_idx].open
            stop_price = ema50.value
            target_price = entry_price + (entry_price - stop_price) * Decimal(2)
            exit_info = _simulate_exit(
                series=series,
                reaction_idx=entry_idx,
                opened_at=d,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                config=config,
            )
            if exit_info is None:
                continue
            exit_date, exit_price, exit_reason = exit_info
            opportunities.append(
                _Opportunity(
                    instrument_id=series.instrument_id,
                    ticker=series.ticker,
                    sector=series.sector,
                    lane=EventBacktestTradeLane.CONTROL,
                    event_date=None,
                    fiscal_period=None,
                    entry_date=series.bars[entry_idx].as_of,
                    entry_price=entry_price,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    score=None,
                    expected_move_pct=None,
                    avg_daily_dollar_volume=None,
                    risk_pct=config.normal_risk_pct,
                )
            )
            exit_idx = next(
                (j for j, b in enumerate(series.bars) if b.as_of == exit_date), len(series.bars)
            )
            in_position_until_idx = exit_idx
    return opportunities


def _spy_buy_and_hold_opportunity(
    universe: SyntheticUniverse, config: BacktestRunConfig
) -> list[_Opportunity]:
    bars = [b for b in universe.benchmark.bars if config.start <= b.as_of <= config.end]
    if len(bars) < 2:
        return []
    entry_price = bars[0].open
    exit_price = bars[-1].close
    return [
        _Opportunity(
            instrument_id=universe.benchmark.instrument_id,
            ticker=universe.benchmark.ticker,
            sector=universe.benchmark.sector,
            lane=EventBacktestTradeLane.CONTROL,
            event_date=None,
            fiscal_period=None,
            entry_date=bars[0].as_of,
            entry_price=entry_price,
            exit_date=bars[-1].as_of,
            exit_price=exit_price,
            exit_reason=EventBacktestExitReason.END_OF_HISTORY,
            score=None,
            expected_move_pct=None,
            avg_daily_dollar_volume=None,
            risk_pct=Decimal(100),
        )
    ]


def _generate_opportunities(
    universe: SyntheticUniverse, config: BacktestRunConfig
) -> tuple[list[_Opportunity], int, int]:
    if config.strategy_key == EventBacktestStrategyKey.EMA_CROSS_COMPARISON:
        return _ema_cross_opportunities(universe, config), 0, 0
    if config.strategy_key == EventBacktestStrategyKey.REGIME_PULLBACK_COMPARISON:
        return _regime_pullback_opportunities(universe, config), 0, 0
    if config.strategy_key == EventBacktestStrategyKey.SPY_BUY_AND_HOLD:
        return _spy_buy_and_hold_opportunity(universe, config), 0, 0
    return _earnings_driven_opportunities(universe, config)


def _allocate_and_execute(
    opportunities: list[_Opportunity], config: BacktestRunConfig
) -> list[SimulatedTrade]:
    """Chronological single-pass allocator enforcing max concurrent
    positions and sector concentration in real time — a position's
    quantity is decided by `compute_tactical_position_size()` using the
    portfolio's actual state (cash + open notional) at the moment of
    entry, and the SPY buy-and-hold control is exempt from every cap
    (it is a benchmark, not a risk-managed strategy)."""
    if config.strategy_key == EventBacktestStrategyKey.SPY_BUY_AND_HOLD:
        return _allocate_buy_and_hold(opportunities, config)

    fee_rate = config.fee_bps / Decimal(10000)
    cash = config.initial_equity
    open_positions: list[_OpenPosition] = []
    trades: list[SimulatedTrade] = []

    for opp in sorted(opportunities, key=lambda o: o.entry_date):
        still_open: list[_OpenPosition] = []
        for pos in open_positions:
            if pos.exit_date <= opp.entry_date:
                cash += pos.exit_notional - pos.exit_fee
            else:
                still_open.append(pos)
        open_positions = still_open

        if len(open_positions) >= config.max_concurrent_positions:
            continue
        sector_notional = sum(
            (p.entry_notional for p in open_positions if p.sector == opp.sector), Decimal(0)
        )
        current_equity = cash + sum((p.entry_notional for p in open_positions), Decimal(0))
        move_for_sizing = (
            opp.expected_move_pct
            if opp.expected_move_pct and opp.expected_move_pct > 0
            else Decimal(5)
        )
        sizing = compute_tactical_position_size(
            account_equity=current_equity,
            risk_budget_pct=opp.risk_pct,
            expected_move_pct=move_for_sizing,
            price=opp.entry_price,
            max_position_pct=config.max_position_pct,
            max_sector_pct=config.max_sector_pct,
            sector_current_notional=sector_notional,
            max_correlated_group_pct=config.max_sector_pct,
            correlated_group_current_notional=sector_notional,
            avg_daily_dollar_volume=opp.avg_daily_dollar_volume or Decimal(10**9),
            max_liquidity_pct_of_adv=config.max_liquidity_pct_of_adv,
            is_speculative_name=opp.lane == EventBacktestTradeLane.PRE_EVENT
            and config.strategy_key == EventBacktestStrategyKey.HYBRID_PRE_AND_POST,
            speculative_position_pct_cap=config.speculative_position_pct_cap,
            available_cash=cash,
            slippage_bps=config.slippage_bps,
        )
        if sizing.final_quantity <= 0:
            continue

        entry_notional = sizing.final_notional
        entry_fee = entry_notional * fee_rate
        cash -= entry_notional + entry_fee
        exit_notional = Decimal(sizing.final_quantity) * opp.exit_price
        exit_fee = exit_notional * fee_rate
        pnl_usd = (exit_notional - entry_notional) - entry_fee - exit_fee
        pnl_pct = (pnl_usd / entry_notional) * Decimal(100) if entry_notional != 0 else Decimal(0)

        open_positions.append(
            _OpenPosition(
                sector=opp.sector,
                exit_date=opp.exit_date,
                entry_notional=entry_notional,
                exit_notional=exit_notional,
                exit_fee=exit_fee,
            )
        )
        trades.append(
            SimulatedTrade(
                instrument_id=opp.instrument_id,
                ticker=opp.ticker,
                sector=opp.sector,
                lane=opp.lane,
                event_date=opp.event_date,
                fiscal_period=opp.fiscal_period,
                entry_date=opp.entry_date,
                entry_price=opp.entry_price,
                exit_date=opp.exit_date,
                exit_price=opp.exit_price,
                quantity=sizing.final_quantity,
                fees_usd=entry_fee + exit_fee,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                exit_reason=opp.exit_reason,
                score=opp.score,
                expected_move_pct=opp.expected_move_pct,
            )
        )

    return trades


def _allocate_buy_and_hold(
    opportunities: list[_Opportunity], config: BacktestRunConfig
) -> list[SimulatedTrade]:
    trades: list[SimulatedTrade] = []
    for opp in opportunities:
        quantity = int(config.initial_equity / opp.entry_price)
        if quantity <= 0:
            continue
        entry_notional = Decimal(quantity) * opp.entry_price
        fee_rate = config.fee_bps / Decimal(10000)
        entry_fee = entry_notional * fee_rate
        exit_notional = Decimal(quantity) * opp.exit_price
        exit_fee = exit_notional * fee_rate
        pnl_usd = (exit_notional - entry_notional) - entry_fee - exit_fee
        pnl_pct = (pnl_usd / entry_notional) * Decimal(100) if entry_notional != 0 else Decimal(0)
        trades.append(
            SimulatedTrade(
                instrument_id=opp.instrument_id,
                ticker=opp.ticker,
                sector=opp.sector,
                lane=opp.lane,
                event_date=None,
                fiscal_period=None,
                entry_date=opp.entry_date,
                entry_price=opp.entry_price,
                exit_date=opp.exit_date,
                exit_price=opp.exit_price,
                quantity=quantity,
                fees_usd=entry_fee + exit_fee,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                exit_reason=opp.exit_reason,
                score=None,
                expected_move_pct=None,
            )
        )
    return trades


def _build_equity_curve(
    trades: list[SimulatedTrade], config: BacktestRunConfig
) -> list[tuple[date, Decimal]]:
    """Realized-cash equity curve: one point at `config.start` (starting
    equity) and one point at each trade's exit date (cumulative realized
    P&L applied) — a documented simplification versus a full daily mark-
    to-market of open positions (the live `services/performance_portfolio.py`'s
    real equity curve does mark open positions daily; this backtest's
    equity curve only moves when a trade actually closes, since a
    position's *unrealized* value during the holding period isn't
    tracked point-in-time by this engine)."""
    if not trades:
        return [(config.start, config.initial_equity), (config.end, config.initial_equity)]
    points: dict[date, Decimal] = {config.start: config.initial_equity}
    running = config.initial_equity
    for trade in sorted(trades, key=lambda t: t.exit_date):
        running += trade.pnl_usd
        points[trade.exit_date] = running
    if config.end not in points:
        points[config.end] = running
    return sorted(points.items())


def run_backtest(db: Session, config: BacktestRunConfig) -> BacktestResult:
    universe = generate_synthetic_universe(
        db,
        start=config.universe_start,
        end=config.universe_end,
        seed=config.seed,
        tickers=config.universe_tickers,
    )
    opportunities, events_seen, events_eligible = _generate_opportunities(universe, config)
    trades = _allocate_and_execute(opportunities, config)
    equity_curve = _build_equity_curve(trades, config)

    equities = [v for _, v in equity_curve]
    daily_returns = daily_returns_from_equity_curve(equities)
    pnls = [t.pnl_usd for t in trades]

    total_return_pct = None
    if equities and equities[0] != 0:
        total_return_pct = ((equities[-1] - equities[0]) / equities[0]) * Decimal(100)

    benchmark_bars = [b for b in universe.benchmark.bars if config.start <= b.as_of <= config.end]
    benchmark_return_pct = None
    if len(benchmark_bars) >= 2 and benchmark_bars[0].close != 0:
        benchmark_return_pct = (
            (benchmark_bars[-1].close - benchmark_bars[0].close) / benchmark_bars[0].close
        ) * Decimal(100)

    return BacktestResult(
        config=config,
        trades=trades,
        equity_curve=equity_curve,
        trade_stats=compute_trade_stats(pnls),
        annualized_volatility_pct=annualized_volatility(daily_returns),
        sharpe_ratio=sharpe_ratio(daily_returns),
        sortino_ratio=sortino_ratio(daily_returns),
        drawdown=max_drawdown(equities),
        total_return_pct=total_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        events_seen=events_seen,
        events_eligible=events_eligible,
    )


__all__ = [
    "METRICS_CALCULATION_VERSION",
    "BacktestResult",
    "BacktestRunConfig",
    "SimulatedTrade",
    "run_backtest",
]
