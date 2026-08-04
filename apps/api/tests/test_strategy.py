"""Pure services/strategy.py tests — compute_comparison_delta, no DB.
Mirrors test_scoring.py/test_backtest_simulation.py's pure-core style."""

from decimal import Decimal

from tradingos_api.schemas.backtest import ResultsSummaryOut
from tradingos_api.services.strategy import compute_comparison_delta


def _summary(
    total_return_pct: Decimal,
    max_drawdown_pct: Decimal,
    win_rate_pct: Decimal,
    avg_win_pct: Decimal,
    avg_loss_pct: Decimal,
    num_trades: int,
) -> ResultsSummaryOut:
    return ResultsSummaryOut(
        ending_equity=Decimal("10000"),
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=win_rate_pct,
        num_trades=num_trades,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        benchmark_return_pct=None,
        equity_curve=[],
        trades=[],
    )


class TestComputeComparisonDelta:
    def test_candidate_better_produces_positive_deltas(self) -> None:
        candidate = _summary(Decimal(20), Decimal(5), Decimal(60), Decimal(8), Decimal(-3), 50)
        active = _summary(Decimal(15), Decimal(8), Decimal(50), Decimal(6), Decimal(-4), 40)

        delta = compute_comparison_delta(candidate, active)

        assert delta.total_return_pct == Decimal(5)
        assert delta.max_drawdown_pct == Decimal(-3)
        assert delta.win_rate_pct == Decimal(10)
        assert delta.avg_win_pct == Decimal(2)
        assert delta.avg_loss_pct == Decimal(1)
        assert delta.num_trades == 10

    def test_candidate_worse_produces_negative_deltas(self) -> None:
        candidate = _summary(Decimal(10), Decimal(12), Decimal(40), Decimal(4), Decimal(-6), 20)
        active = _summary(Decimal(15), Decimal(8), Decimal(50), Decimal(6), Decimal(-4), 40)

        delta = compute_comparison_delta(candidate, active)

        assert delta.total_return_pct == Decimal(-5)
        assert delta.max_drawdown_pct == Decimal(4)
        assert delta.win_rate_pct == Decimal(-10)
        assert delta.num_trades == -20

    def test_identical_summaries_produce_zero_deltas(self) -> None:
        summary = _summary(Decimal(10), Decimal(5), Decimal(50), Decimal(5), Decimal(-5), 30)

        delta = compute_comparison_delta(summary, summary)

        assert delta.total_return_pct == Decimal(0)
        assert delta.max_drawdown_pct == Decimal(0)
        assert delta.win_rate_pct == Decimal(0)
        assert delta.avg_win_pct == Decimal(0)
        assert delta.avg_loss_pct == Decimal(0)
        assert delta.num_trades == 0
