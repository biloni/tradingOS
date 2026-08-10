"""Event-driven backtest engine tests (Revision Prompt 13) — the
required "no-look-ahead" category, eligibility-gate known vectors,
allocator cap enforcement, fee application, and a full-run sanity check
for all 8 strategy variants."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    EventBacktestExitReason,
    EventBacktestStrategyKey,
    EventBacktestTradeLane,
)
from tradingos_api.services.backtest_data import generate_synthetic_universe
from tradingos_api.services.backtest_engine import (
    BacktestRunConfig,
    _allocate_and_execute,
    _evaluate_earnings_event,
    _Opportunity,
    _passes_eligibility_gate,
    _simulate_exit,
    run_backtest,
)

_UNIVERSE_START = date(2024, 8, 1)
_UNIVERSE_END = date(2026, 7, 31)


class TestEligibilityGateKnownVectors:
    def test_all_conditions_pass(self) -> None:
        assert _passes_eligibility_gate(
            score_total=6,
            score_threshold=5,
            expected_move_pct=Decimal(5),
            move_threshold_pct=Decimal(4),
            avg_daily_dollar_volume=Decimal(60_000_000),
            min_avg_daily_dollar_volume=Decimal(50_000_000),
            num_analysts=4,
            min_analysts=3,
        )

    def test_score_below_threshold_fails(self) -> None:
        assert not _passes_eligibility_gate(
            score_total=4,
            score_threshold=5,
            expected_move_pct=Decimal(5),
            move_threshold_pct=Decimal(4),
            avg_daily_dollar_volume=Decimal(60_000_000),
            min_avg_daily_dollar_volume=Decimal(50_000_000),
            num_analysts=4,
            min_analysts=3,
        )

    def test_expected_move_none_fails(self) -> None:
        assert not _passes_eligibility_gate(
            score_total=8,
            score_threshold=5,
            expected_move_pct=None,
            move_threshold_pct=Decimal(4),
            avg_daily_dollar_volume=Decimal(60_000_000),
            min_avg_daily_dollar_volume=Decimal(50_000_000),
            num_analysts=4,
            min_analysts=3,
        )

    def test_liquidity_below_minimum_fails(self) -> None:
        assert not _passes_eligibility_gate(
            score_total=8,
            score_threshold=5,
            expected_move_pct=Decimal(5),
            move_threshold_pct=Decimal(4),
            avg_daily_dollar_volume=Decimal(1_000_000),
            min_avg_daily_dollar_volume=Decimal(50_000_000),
            num_analysts=4,
            min_analysts=3,
        )

    def test_analyst_coverage_below_minimum_fails(self) -> None:
        assert not _passes_eligibility_gate(
            score_total=8,
            score_threshold=5,
            expected_move_pct=Decimal(5),
            move_threshold_pct=Decimal(4),
            avg_daily_dollar_volume=Decimal(60_000_000),
            min_avg_daily_dollar_volume=Decimal(50_000_000),
            num_analysts=1,
            min_analysts=3,
        )


class TestNoLookAhead:
    """The required "no-look-ahead" test category: a past earnings
    event's score/expected-move/liquidity evaluation must never change
    based on that event's own (or a later event's) realized outcome."""

    def test_mutating_this_events_own_realized_gap_does_not_change_its_evaluation(
        self, db_session: Session
    ) -> None:
        universe = generate_synthetic_universe(
            db_session, start=_UNIVERSE_START, end=_UNIVERSE_END
        )
        series = next(i for i in universe.instruments if len(i.earnings_events) >= 3)
        event_idx = 2
        original = _evaluate_earnings_event(
            series=series,
            event_idx=event_idx,
            universe=universe,
            config=BacktestRunConfig(strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE),
        )

        mutated_event = dataclasses.replace(
            series.earnings_events[event_idx], actual_gap_pct=Decimal("99.0")
        )
        mutated_events = list(series.earnings_events)
        mutated_events[event_idx] = mutated_event
        mutated_series = dataclasses.replace(series, earnings_events=mutated_events)

        mutated = _evaluate_earnings_event(
            series=mutated_series,
            event_idx=event_idx,
            universe=universe,
            config=BacktestRunConfig(strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE),
        )
        assert original == mutated

    def test_mutating_a_later_events_gap_does_not_change_an_earlier_evaluation(
        self, db_session: Session
    ) -> None:
        universe = generate_synthetic_universe(
            db_session, start=_UNIVERSE_START, end=_UNIVERSE_END
        )
        series = next(i for i in universe.instruments if len(i.earnings_events) >= 4)
        earlier_idx, later_idx = 1, 3
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE
        )
        original = _evaluate_earnings_event(
            series=series, event_idx=earlier_idx, universe=universe, config=config
        )

        mutated_events = list(series.earnings_events)
        mutated_events[later_idx] = dataclasses.replace(
            mutated_events[later_idx], actual_gap_pct=Decimal("-99.0")
        )
        mutated_series = dataclasses.replace(series, earnings_events=mutated_events)
        mutated = _evaluate_earnings_event(
            series=mutated_series, event_idx=earlier_idx, universe=universe, config=config
        )
        assert original == mutated

    def test_mutating_bars_strictly_after_the_report_date_does_not_change_the_score(
        self, db_session: Session
    ) -> None:
        universe = generate_synthetic_universe(
            db_session, start=_UNIVERSE_START, end=_UNIVERSE_END
        )
        series = next(i for i in universe.instruments if len(i.earnings_events) >= 2)
        event_idx = 1
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE
        )
        original = _evaluate_earnings_event(
            series=series, event_idx=event_idx, universe=universe, config=config
        )

        report_date = series.earnings_events[event_idx].report_date
        mutated_bars = [
            dataclasses.replace(b, close=b.close * Decimal(5), high=b.high * Decimal(5))
            if b.as_of > report_date
            else b
            for b in series.bars
        ]
        mutated_series = dataclasses.replace(series, bars=mutated_bars)
        mutated = _evaluate_earnings_event(
            series=mutated_series, event_idx=event_idx, universe=universe, config=config
        )
        assert original == mutated


class TestSimulateExitWiring:
    def test_stop_hit_maps_to_stop_exit_reason(self, db_session: Session) -> None:
        universe = generate_synthetic_universe(
            db_session, start=_UNIVERSE_START, end=_UNIVERSE_END
        )
        series = universe.instruments[0]
        reaction_idx = 100
        entry_price = series.bars[reaction_idx].open
        exit_info = _simulate_exit(
            series=series,
            reaction_idx=reaction_idx,
            opened_at=series.bars[reaction_idx - 1].as_of,
            entry_price=entry_price,
            stop_price=entry_price * Decimal(2),
            target_price=entry_price * Decimal(3),
            config=BacktestRunConfig(strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE),
        )
        assert exit_info is not None
        assert exit_info[2] == EventBacktestExitReason.STOP


def _opportunity(
    *,
    ticker: str = "AMD",
    sector: str | None = "Technology",
    entry_date: date,
    exit_date: date,
    entry_price: Decimal = Decimal(100),
    exit_price: Decimal = Decimal(110),
    expected_move_pct: Decimal = Decimal(5),
) -> _Opportunity:
    return _Opportunity(
        instrument_id=uuid.uuid4(),
        ticker=ticker,
        sector=sector,
        lane=EventBacktestTradeLane.PRE_EVENT,
        event_date=entry_date,
        fiscal_period="Q1-2025",
        entry_date=entry_date,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason=EventBacktestExitReason.TARGET,
        score=Decimal(7),
        expected_move_pct=expected_move_pct,
        avg_daily_dollar_volume=Decimal(100_000_000),
        risk_pct=Decimal("0.50"),
    )


class TestAllocatorCaps:
    def test_max_concurrent_positions_is_enforced(self) -> None:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            max_concurrent_positions=1,
        )
        opportunities = [
            _opportunity(entry_date=date(2025, 1, 2), exit_date=date(2025, 1, 20)),
            _opportunity(entry_date=date(2025, 1, 5), exit_date=date(2025, 1, 25)),
        ]
        trades = _allocate_and_execute(opportunities, config)
        assert len(trades) == 1

    def test_second_position_taken_after_first_closes(self) -> None:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            max_concurrent_positions=1,
        )
        opportunities = [
            _opportunity(entry_date=date(2025, 1, 2), exit_date=date(2025, 1, 10)),
            _opportunity(entry_date=date(2025, 1, 15), exit_date=date(2025, 1, 25)),
        ]
        trades = _allocate_and_execute(opportunities, config)
        assert len(trades) == 2

    def test_sector_cap_blocks_concentrated_exposure(self) -> None:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            max_concurrent_positions=10,
            max_sector_pct=Decimal("15.00"),
            max_position_pct=Decimal("15.00"),
        )
        opportunities = [
            _opportunity(
                ticker=f"NAME{i}", entry_date=date(2025, 1, 2), exit_date=date(2025, 1, 20)
            )
            for i in range(5)
        ]
        trades = _allocate_and_execute(opportunities, config)
        assert len(trades) < 5

    def test_fee_is_subtracted_from_pnl_both_legs(self) -> None:
        config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            max_concurrent_positions=5,
            fee_bps=Decimal(5),
            initial_equity=Decimal(10000),
        )
        opportunities = [
            _opportunity(
                entry_date=date(2025, 1, 2),
                exit_date=date(2025, 1, 20),
                entry_price=Decimal(100),
                exit_price=Decimal(110),
            )
        ]
        trades = _allocate_and_execute(opportunities, config)
        assert len(trades) == 1
        trade = trades[0]
        gross_pnl = Decimal(trade.quantity) * (trade.exit_price - trade.entry_price)
        assert trade.pnl_usd == gross_pnl - trade.fees_usd
        assert trade.fees_usd > 0


class TestFullRunAllStrategies:
    def test_every_strategy_runs_without_error_and_produces_a_valid_result(
        self, db_session: Session
    ) -> None:
        for key in EventBacktestStrategyKey:
            config = BacktestRunConfig(
                strategy_key=key,
                start=date(2026, 1, 1),
                end=date(2026, 7, 31),
                universe_start=_UNIVERSE_START,
                universe_end=_UNIVERSE_END,
            )
            result = run_backtest(db_session, config)
            assert result.equity_curve[0][1] == config.initial_equity
            for trade in result.trades:
                assert config.start <= trade.entry_date <= config.end
                assert trade.exit_date >= trade.entry_date
                assert trade.quantity > 0
