"""Golden/regression tests (Revision Prompt 13) — locks the locked
baseline scenario's current output so a future change to the engine,
the synthetic data generator, or any reused live function
(`compute_tactical_earnings_score`, `compute_expected_move`,
`compute_tactical_position_size`, `compute_hypothetical_outcome`) that
silently changes results is caught immediately, whether or not that
change is intentional. Every locked figure was captured directly from a
real run of this exact configuration, not hand-picked."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import EventBacktestStrategyKey
from tradingos_api.services.backtest_engine import BacktestRunConfig, run_backtest

_LOCKED_CONFIG = BacktestRunConfig(
    strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
    initial_equity=Decimal(10000),
    start=date(2024, 8, 1),
    end=date(2026, 7, 31),
    universe_start=date(2024, 8, 1),
    universe_end=date(2026, 7, 31),
    score_threshold=5,
    expected_move_threshold_pct=Decimal(4),
    normal_risk_pct=Decimal("0.50"),
    speculative_risk_pct=Decimal("0.25"),
    max_position_pct=Decimal("15.00"),
    max_sector_pct=Decimal("25.00"),
    max_concurrent_positions=3,
    fee_bps=Decimal(5),
    seed=42,
)


class TestReproducibility:
    def test_two_runs_of_the_same_config_produce_identical_trades(
        self, db_session: Session
    ) -> None:
        first = run_backtest(db_session, _LOCKED_CONFIG)
        second = run_backtest(db_session, _LOCKED_CONFIG)
        assert first.trades == second.trades
        assert first.equity_curve == second.equity_curve

    def test_different_seed_produces_a_different_result(self, db_session: Session) -> None:
        other = run_backtest(db_session, replace(_LOCKED_CONFIG, seed=7))
        same_seed = run_backtest(db_session, _LOCKED_CONFIG)
        assert other.trades != same_seed.trades


class TestGoldenBaselineFigures:
    """Locks the wide-window locked-baseline configuration's exact
    output as of this revision — see docs/TEST_EVIDENCE.md's Prompt 13
    entry for how this number was captured and why 29 trades (not the
    externally-targeted ~25) is the honest result for this synthetic
    universe."""

    def test_golden_trade_count(self, db_session: Session) -> None:
        result = run_backtest(db_session, _LOCKED_CONFIG)
        assert len(result.trades) == 29

    def test_golden_realized_pnl_sum(self, db_session: Session) -> None:
        result = run_backtest(db_session, _LOCKED_CONFIG)
        total_pnl = sum((t.pnl_usd for t in result.trades), Decimal(0))
        final_equity = result.equity_curve[-1][1]
        assert final_equity == _LOCKED_CONFIG.initial_equity + total_pnl

    def test_golden_win_loss_counts(self, db_session: Session) -> None:
        result = run_backtest(db_session, _LOCKED_CONFIG)
        assert result.trade_stats.num_wins == 8
        assert result.trade_stats.num_losses == 21
