"""Performance-statistics primitive tests (Revision Prompt 12) — every
formula in `services/performance_metrics.py` checked against a hand-
computed known vector, plus the sparse-sample, cash-flow, and
benchmark-calendar edge cases the prompt requires explicitly."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingos_api.services.performance_metrics import (
    CashFlow,
    align_return_series,
    annualized_volatility,
    beta_alpha,
    compute_trade_stats,
    concentration_hhi,
    daily_returns_from_equity_curve,
    max_drawdown,
    money_weighted_return_irr,
    sharpe_ratio,
    sortino_ratio,
    time_weighted_return,
    turnover_pct,
)

TOL = Decimal("0.0001")


def _close(a: Decimal, b: Decimal, tol: Decimal = TOL) -> bool:
    return abs(a - b) <= tol


class TestDailyReturnsAndTWR:
    def test_daily_returns_known_vector(self) -> None:
        curve = [Decimal(100), Decimal(110), Decimal(99)]
        returns = daily_returns_from_equity_curve(curve)
        assert returns == [Decimal("0.1"), Decimal("-0.1")]

    def test_twr_chains_sub_period_returns_geometrically(self) -> None:
        # +10% then -10% is NOT flat (0.99), the classic volatility-drag example.
        result = time_weighted_return([Decimal("0.10"), Decimal("-0.10")])
        assert _close(result, Decimal("-0.01"))

    def test_twr_empty_is_zero(self) -> None:
        assert time_weighted_return([]) == Decimal(0)


class TestMoneyWeightedReturnIRR:
    def test_known_vector_ten_percent_annual(self) -> None:
        # Invest $1000, receive $1100 exactly one year later -> 10% IRR.
        flows = [CashFlow(0, Decimal(-1000)), CashFlow(365, Decimal(1100))]
        irr = money_weighted_return_irr(flows)
        assert irr is not None
        assert _close(irr, Decimal("0.10"), Decimal("0.0005"))

    def test_sparse_single_flow_returns_none(self) -> None:
        assert money_weighted_return_irr([CashFlow(0, Decimal(-1000))]) is None

    def test_same_sign_flows_have_no_valid_irr(self) -> None:
        # Two deposits, no eventual payout to solve against.
        flows = [CashFlow(0, Decimal(-1000)), CashFlow(100, Decimal(-500))]
        assert money_weighted_return_irr(flows) is None

    def test_irregular_intermediate_cash_flow(self) -> None:
        # Deposit, mid-period top-up, then a payout larger than the sum
        # of deposits -- must still resolve to a positive IRR without
        # raising, exercising the "cash flows" required test category
        # with more than the minimal two-flow vector.
        flows = [
            CashFlow(0, Decimal(-1000)),
            CashFlow(180, Decimal(-500)),
            CashFlow(365, Decimal(1700)),
        ]
        irr = money_weighted_return_irr(flows)
        assert irr is not None
        assert irr > 0


class TestSharpeAndSortino:
    def test_sharpe_known_vector(self) -> None:
        returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("-0.01"),
            Decimal("0.03"),
            Decimal("0"),
        ]
        result = sharpe_ratio(returns, periods_per_year=252)
        assert result is not None
        # mean=0.01, population stdev=sqrt(0.0002)=0.01414213..., *sqrt(252)=15.8745...
        expected = (Decimal("0.01") / Decimal("0.0002").sqrt()) * Decimal(252).sqrt()
        assert _close(result, expected, Decimal("0.001"))

    def test_sortino_ignores_upside_volatility(self) -> None:
        # All positive returns of varying size -> no downside observation at all.
        returns = [Decimal("0.01"), Decimal("0.05"), Decimal("0.02")]
        assert sortino_ratio(returns) is None

    def test_sortino_known_vector_only_penalizes_losses(self) -> None:
        returns = [Decimal("0.02"), Decimal("-0.01"), Decimal("0.03"), Decimal("-0.02")]
        result = sortino_ratio(returns, periods_per_year=252)
        assert result is not None
        mean = Decimal("0.005")
        downside_sq = [min(r, Decimal(0)) ** 2 for r in returns]
        downside_dev = (sum(downside_sq, Decimal(0)) / Decimal(4)).sqrt()
        expected = (mean / downside_dev) * Decimal(252).sqrt()
        assert _close(result, expected, Decimal("0.001"))

    def test_sparse_sample_single_return_is_none(self) -> None:
        assert sharpe_ratio([Decimal("0.01")]) is None
        assert sortino_ratio([Decimal("0.01")]) is None

    def test_zero_volatility_sharpe_is_none(self) -> None:
        assert sharpe_ratio([Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]) is None

    def test_annualized_volatility_known_vector(self) -> None:
        returns = [Decimal("0.01"), Decimal("-0.01")]
        result = annualized_volatility(returns, periods_per_year=252)
        assert result is not None
        assert _close(result, Decimal("0.01") * Decimal(252).sqrt(), Decimal("0.001"))


class TestMaxDrawdown:
    def test_known_vector(self) -> None:
        curve = [Decimal(v) for v in [100, 110, 90, 95, 120, 80, 130]]
        result = max_drawdown(curve)
        assert _close(result.max_drawdown_pct, Decimal("-0.333333"), Decimal("0.001"))
        assert result.peak_index == 4
        assert result.trough_index == 5
        assert result.recovery_index == 6
        assert result.recovery_periods == 1

    def test_monotonically_rising_curve_has_zero_drawdown(self) -> None:
        curve = [Decimal(v) for v in [100, 105, 110, 120]]
        result = max_drawdown(curve)
        assert result.max_drawdown_pct == Decimal(0)

    def test_never_recovered_by_end_of_series(self) -> None:
        curve = [Decimal(v) for v in [100, 120, 80]]
        result = max_drawdown(curve)
        assert result.recovery_index is None
        assert result.recovery_periods is None

    def test_sparse_single_point_curve(self) -> None:
        result = max_drawdown([Decimal(100)])
        assert result.max_drawdown_pct == Decimal(0)
        assert result.peak_index is None


class TestTradeStats:
    def test_known_vector(self) -> None:
        pnls = [Decimal(v) for v in [100, -50, 200, -100, 0, 50]]
        result = compute_trade_stats(pnls)
        assert result.num_trades == 6
        assert result.num_wins == 3
        assert result.num_losses == 2
        assert result.num_breakeven == 1
        assert result.win_rate_pct == Decimal(50)
        assert _close(result.avg_win, Decimal("116.6667"), Decimal("0.001"))
        assert result.avg_loss == Decimal("-75")
        assert _close(result.payoff_ratio, Decimal("1.5556"), Decimal("0.001"))
        assert _close(result.profit_factor, Decimal("2.3333"), Decimal("0.001"))
        assert _close(result.expectancy, Decimal("33.3333"), Decimal("0.001"))

    def test_sparse_empty_sample(self) -> None:
        result = compute_trade_stats([])
        assert result.num_trades == 0
        assert result.win_rate_pct is None
        assert result.profit_factor is None
        assert result.expectancy is None

    def test_sparse_single_win_no_losses(self) -> None:
        result = compute_trade_stats([Decimal(100)])
        assert result.win_rate_pct == Decimal(100)
        assert result.avg_loss is None
        assert result.payoff_ratio is None
        assert result.profit_factor is None  # no losses to divide against
        assert result.expectancy == Decimal(100)

    def test_sparse_single_loss_no_wins(self) -> None:
        result = compute_trade_stats([Decimal(-50)])
        assert result.win_rate_pct == Decimal(0)
        assert result.avg_win is None
        assert result.payoff_ratio is None
        assert result.profit_factor == Decimal(0)


class TestBetaAlpha:
    def test_known_vector_beta_exactly_two_alpha_zero(self) -> None:
        benchmark = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.03")]
        portfolio = [r * Decimal(2) for r in benchmark]
        beta, alpha = beta_alpha(portfolio, benchmark, periods_per_year=252)
        assert beta is not None and alpha is not None
        assert _close(beta, Decimal(2), Decimal("0.0001"))
        assert _close(alpha, Decimal(0), Decimal("0.0001"))

    def test_sparse_sample_returns_none(self) -> None:
        beta, alpha = beta_alpha([Decimal("0.01")], [Decimal("0.01")])
        assert beta is None and alpha is None

    def test_zero_variance_benchmark_returns_none(self) -> None:
        beta, alpha = beta_alpha(
            [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")],
            [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")],
        )
        assert beta is None and alpha is None


class TestBenchmarkCalendarAlignment:
    def test_inner_join_drops_dates_only_one_side_has(self) -> None:
        # Portfolio traded on a benchmark holiday; benchmark has a date
        # (e.g. a half-day) the portfolio series doesn't carry.
        portfolio = [
            (date(2026, 1, 2), Decimal("0.01")),
            (date(2026, 1, 3), Decimal("0.02")),  # benchmark holiday
            (date(2026, 1, 5), Decimal("-0.01")),
        ]
        benchmark = [
            (date(2026, 1, 2), Decimal("0.005")),
            (date(2026, 1, 4), Decimal("0.03")),  # portfolio didn't trade
            (date(2026, 1, 5), Decimal("-0.005")),
        ]
        aligned_p, aligned_b = align_return_series(portfolio, benchmark)
        assert aligned_p == [Decimal("0.01"), Decimal("-0.01")]
        assert aligned_b == [Decimal("0.005"), Decimal("-0.005")]

    def test_no_overlapping_dates_returns_empty(self) -> None:
        portfolio = [(date(2026, 1, 2), Decimal("0.01"))]
        benchmark = [(date(2026, 1, 3), Decimal("0.02"))]
        aligned_p, aligned_b = align_return_series(portfolio, benchmark)
        assert aligned_p == []
        assert aligned_b == []


class TestExposureTurnoverConcentration:
    def test_turnover_uses_lesser_of_buys_or_sells(self) -> None:
        result = turnover_pct(Decimal(5000), Decimal(3000), Decimal(20000))
        assert result == Decimal(15)  # min(5000,3000)/20000 * 100

    def test_turnover_zero_equity_is_none(self) -> None:
        assert turnover_pct(Decimal(1000), Decimal(500), Decimal(0)) is None

    def test_concentration_hhi_equal_weighted(self) -> None:
        # 4 equal 25% positions -> HHI = 4 * (0.25)^2 = 0.25
        result = concentration_hhi([Decimal(25)] * 4)
        assert _close(result, Decimal("0.25"))

    def test_concentration_hhi_fully_concentrated(self) -> None:
        result = concentration_hhi([Decimal(100)])
        assert result == Decimal(1)

    def test_concentration_hhi_empty_portfolio(self) -> None:
        assert concentration_hhi([]) == Decimal(0)
