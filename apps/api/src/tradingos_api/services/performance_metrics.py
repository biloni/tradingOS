"""Shared, DB-free performance-statistics primitives (Revision Prompt 12).
Every function here is a pure function over plain `Decimal`/`date`
inputs — no ORM, no session — so the exact same math backs both the
live-portfolio performance layer (`services/performance_portfolio.py`)
and Revision Prompt 13's backtest engine, rather than two independently
maintained (and inevitably drifting) implementations of Sharpe/Sortino/
drawdown/profit-factor. This mirrors `services/analytics.py`'s own
"pure Python + Decimal, no numpy/pandas" discipline and its
`IndicatorResult`-style honesty about missing/insufficient data —
extended here to portfolio-level statistics, none of which existed
anywhere in this codebase before this revision (confirmed by grep: no
prior Sharpe/Sortino/profit-factor/expectancy implementation, live or
retired).

`Decimal.ln()`/`.exp()` (both native `decimal` module methods) are used
for the IRR solver's fractional-exponent discounting, keeping money-
weighted return in `Decimal` throughout rather than dropping to `float`
for "just the statistics" — consistent with "never float-math currency"
even though a rate of return is not itself a currency amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

CALCULATION_VERSION = "v1"

TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = Decimal(365)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _stdev(values: list[Decimal], *, mean: Decimal | None = None) -> Decimal:
    """Population standard deviation (divides by N, not N-1) — matches
    `services/analytics.py::realized_volatility()`'s own convention, so
    a portfolio-level volatility figure and an instrument-level one are
    computed the same way if ever compared side by side."""
    m = mean if mean is not None else _mean(values)
    variance = sum(((v - m) ** 2 for v in values), Decimal(0)) / Decimal(len(values))
    return variance.sqrt()


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


def daily_returns_from_equity_curve(equity_curve: list[Decimal]) -> list[Decimal]:
    """Simple period-over-period returns with no external-flow
    adjustment — correct for a backtest (all equity changes are
    strategy P&L) and for any equity-curve segment known to be
    flow-free. A live account with deposits/withdrawals between two
    curve points must use `time_weighted_return()`'s sub-period
    boundaries instead, not this function across the flow."""
    returns: list[Decimal] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev == 0:
            continue
        returns.append((equity_curve[i] - prev) / prev)
    return returns


def time_weighted_return(sub_period_returns: list[Decimal]) -> Decimal:
    """Chain-links already-computed sub-period returns (each excluding
    the effect of an external cash flow at its boundary — the caller
    computes each sub-period as `(value_just_before_next_flow -
    value_just_after_previous_flow) / value_just_after_previous_flow`,
    the standard TWR construction) into one cumulative return. An empty
    input returns `0` (no periods, no return), not an error — a fresh
    account's very first day is a valid, if trivial, TWR calculation."""
    product = Decimal(1)
    for r in sub_period_returns:
        product *= Decimal(1) + r
    return product - Decimal(1)


@dataclass(frozen=True)
class CashFlow:
    days_from_start: int
    amount: Decimal
    """Negative for money going into the account (a deposit, or the
    initial investment), positive for money coming out (a withdrawal,
    or the final liquidation value on the valuation date) — the
    standard IRR sign convention."""


def money_weighted_return_irr(
    cash_flows: list[CashFlow],
    *,
    tolerance: Decimal = Decimal("0.0000001"),
    max_iterations: int = 200,
) -> Decimal | None:
    """Solves for the *annualized* rate `r` such that
    `sum(amount_i / (1+r)^(days_i/365))` is zero, via bisection (always
    convergent for a well-posed IRR problem, unlike Newton-Raphson,
    which can diverge on a poorly-scaled initial guess) over
    `Decimal.ln()`/`.exp()` rather than `float`. Returns `None` when the
    flows don't bracket a root (e.g. all same sign — no valid IRR
    exists, most commonly a sparse-sample edge case: a single flow, or
    every flow moving the same direction with no eventual payout to
    solve against) rather than raising or fabricating a value."""
    if len(cash_flows) < 2:
        return None

    def npv(rate: Decimal) -> Decimal | None:
        total = Decimal(0)
        base = Decimal(1) + rate
        if base <= 0:
            return None
        for cf in cash_flows:
            exponent = Decimal(cf.days_from_start) / CALENDAR_DAYS_PER_YEAR
            try:
                discount = (exponent * base.ln()).exp()
            except InvalidOperation:
                return None
            total += cf.amount / discount
        return total

    low, high = Decimal("-0.9999"), Decimal(10)
    npv_low, npv_high = npv(low), npv(high)
    if npv_low is None or npv_high is None or npv_low * npv_high > 0:
        return None

    for _ in range(max_iterations):
        mid = (low + high) / Decimal(2)
        npv_mid = npv(mid)
        if npv_mid is None:
            return None
        if abs(npv_mid) < tolerance:
            return mid
        if (npv_low is not None) and npv_low * npv_mid < 0:
            high, npv_high = mid, npv_mid
        else:
            low, npv_low = mid, npv_mid
    return (low + high) / Decimal(2)


# ---------------------------------------------------------------------------
# Risk-adjusted return
# ---------------------------------------------------------------------------


def annualized_volatility(
    returns: list[Decimal], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> Decimal | None:
    if len(returns) < 2:
        return None
    return _stdev(returns) * Decimal(periods_per_year).sqrt()


def sharpe_ratio(
    returns: list[Decimal],
    *,
    risk_free_rate_annual: Decimal = Decimal(0),
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> Decimal | None:
    """`(mean(excess_returns) / stdev(returns)) * sqrt(periods_per_year)`
    — the per-period risk-free rate is compounded down from the annual
    rate (`(1+rf_annual)^(1/periods_per_year) - 1`), never simply
    divided by `periods_per_year`, since that linear approximation
    diverges from the compounding convention the rest of this module
    uses for annualization."""
    if len(returns) < 2:
        return None
    stdev = _stdev(returns)
    if stdev == 0:
        return None
    rf_per_period = _annual_rate_to_per_period(risk_free_rate_annual, periods_per_year)
    excess_mean = _mean(returns) - rf_per_period
    return (excess_mean / stdev) * Decimal(periods_per_year).sqrt()


def sortino_ratio(
    returns: list[Decimal],
    *,
    risk_free_rate_annual: Decimal = Decimal(0),
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> Decimal | None:
    """Same construction as `sharpe_ratio()` but the denominator is
    downside deviation only (`sqrt(mean(min(r - target, 0)^2))`,
    target = the per-period risk-free rate) — upside volatility never
    penalizes the ratio. `None` when there is no downside observation
    at all (every period beat the target) rather than a divide-by-zero
    or a fabricated "infinite" score."""
    if len(returns) < 2:
        return None
    rf_per_period = _annual_rate_to_per_period(risk_free_rate_annual, periods_per_year)
    downside_sq = [min(r - rf_per_period, Decimal(0)) ** 2 for r in returns]
    downside_variance = sum(downside_sq, Decimal(0)) / Decimal(len(returns))
    if downside_variance == 0:
        return None
    downside_deviation = downside_variance.sqrt()
    excess_mean = _mean(returns) - rf_per_period
    return (excess_mean / downside_deviation) * Decimal(periods_per_year).sqrt()


def _annual_rate_to_per_period(annual_rate: Decimal, periods_per_year: int) -> Decimal:
    if annual_rate == 0:
        return Decimal(0)
    base = Decimal(1) + annual_rate
    exponent = Decimal(1) / Decimal(periods_per_year)
    return (exponent * base.ln()).exp() - Decimal(1)


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawdownResult:
    max_drawdown_pct: Decimal
    """Zero or negative — `-0.15` means a 15% peak-to-trough decline."""
    peak_index: int | None
    trough_index: int | None
    recovery_index: int | None
    """Index of the first point back at/above the pre-drawdown peak, or
    `None` if the series ends still in drawdown — never guessed."""
    recovery_periods: int | None
    """`recovery_index - trough_index`, or `None` alongside
    `recovery_index=None`."""


def max_drawdown(equity_curve: list[Decimal]) -> DrawdownResult:
    if len(equity_curve) < 2:
        return DrawdownResult(Decimal(0), None, None, None, None)

    peak = equity_curve[0]
    peak_index = 0
    worst_dd = Decimal(0)
    worst_peak_index: int | None = None
    worst_trough_index: int | None = None

    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            peak_index = i
        if peak == 0:
            continue
        dd = (value - peak) / peak
        if dd < worst_dd:
            worst_dd = dd
            worst_peak_index = peak_index
            worst_trough_index = i

    recovery_index: int | None = None
    if worst_peak_index is not None and worst_trough_index is not None:
        peak_value = equity_curve[worst_peak_index]
        for i in range(worst_trough_index + 1, len(equity_curve)):
            if equity_curve[i] >= peak_value:
                recovery_index = i
                break

    recovery_periods = (
        recovery_index - worst_trough_index
        if recovery_index is not None and worst_trough_index is not None
        else None
    )
    return DrawdownResult(
        max_drawdown_pct=worst_dd,
        peak_index=worst_peak_index,
        trough_index=worst_trough_index,
        recovery_index=recovery_index,
        recovery_periods=recovery_periods,
    )


# ---------------------------------------------------------------------------
# Trade-level statistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeStatsResult:
    num_trades: int
    num_wins: int
    num_losses: int
    num_breakeven: int
    win_rate_pct: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    """Negative or zero — the average size of a losing trade, sign
    preserved (never reported as a positive magnitude) so `expectancy`
    below can add it directly."""
    payoff_ratio: Decimal | None
    """`avg_win / abs(avg_loss)` — `None` if there are no losses to
    divide by (a perfect win rate) or no wins (nothing to size against)."""
    profit_factor: Decimal | None
    """`sum(wins) / abs(sum(losses))` — `None` (not infinite) if there
    are zero losing trades; the win-rate/payoff-ratio fields already
    communicate "no losses yet" without a fabricated infinite ratio."""
    expectancy: Decimal | None
    """Average realized P&L per trade — `win_rate * avg_win + (1 -
    win_rate) * avg_loss`, equivalently just `mean(realized_pnls)`; kept
    as an explicit formula for documentation clarity even though the
    two are algebraically identical."""


def compute_trade_stats(realized_pnls: list[Decimal]) -> TradeStatsResult:
    """`realized_pnls` must contain only *closed* trades/legs — an open
    position's unrealized P&L does not belong in a win-rate/profit-
    factor calculation (it can still reverse) and must be excluded by
    the caller before this function ever sees it."""
    wins = [p for p in realized_pnls if p > 0]
    losses = [p for p in realized_pnls if p < 0]
    breakeven = [p for p in realized_pnls if p == 0]
    n = len(realized_pnls)

    win_rate = Decimal(len(wins)) / Decimal(n) * Decimal(100) if n > 0 else None
    avg_win = _mean(wins) if wins else None
    avg_loss = _mean(losses) if losses else None

    payoff_ratio = None
    if avg_win is not None and avg_loss is not None and avg_loss != 0:
        payoff_ratio = avg_win / abs(avg_loss)

    profit_factor = None
    if losses:
        gross_loss = abs(sum(losses, Decimal(0)))
        if gross_loss != 0:
            profit_factor = sum(wins, Decimal(0)) / gross_loss

    expectancy = _mean(realized_pnls) if realized_pnls else None

    return TradeStatsResult(
        num_trades=n,
        num_wins=len(wins),
        num_losses=len(losses),
        num_breakeven=len(breakeven),
        win_rate_pct=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff_ratio,
        profit_factor=profit_factor,
        expectancy=expectancy,
    )


# ---------------------------------------------------------------------------
# Benchmark relation
# ---------------------------------------------------------------------------


def beta_alpha(
    portfolio_returns: list[Decimal],
    benchmark_returns: list[Decimal],
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> tuple[Decimal | None, Decimal | None]:
    """`beta = cov(portfolio, benchmark) / var(benchmark)`, `alpha =
    annualized(mean(portfolio)) - beta * annualized(mean(benchmark))` —
    a single-factor regression against one benchmark, not a full CAPM
    fit (no risk-free subtraction here; `sharpe_ratio()`/`sortino_ratio()`
    are where the risk-free rate enters this module). Both series must
    already be aligned (same length, same period), the caller's
    responsibility, not this function's — a length mismatch is treated
    as `min(len(a), len(b))` truncated from the start, which a caller
    that actually cares about calendar alignment should never rely on
    (see `align_return_series()`)."""
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 3:
        return None, None
    p = portfolio_returns[-n:]
    b = benchmark_returns[-n:]
    mean_p = _mean(p)
    mean_b = _mean(b)
    covariance = sum(((x - mean_p) * (y - mean_b) for x, y in zip(p, b, strict=True)), Decimal(0))
    variance_b = sum(((y - mean_b) ** 2 for y in b), Decimal(0))
    if variance_b == 0:
        return None, None
    beta = covariance / variance_b
    annualized_p = mean_p * Decimal(periods_per_year)
    annualized_b = mean_b * Decimal(periods_per_year)
    alpha = annualized_p - beta * annualized_b
    return beta, alpha


def align_return_series(
    dated_returns_a: list[tuple[date, Decimal]], dated_returns_b: list[tuple[date, Decimal]]
) -> tuple[list[Decimal], list[Decimal]]:
    """Inner-joins two dated return series on their date, discarding any
    date only one side has (a benchmark holiday the portfolio doesn't
    observe, or vice versa) — the "benchmark calendars" required test
    category exists specifically to prove this join is exact rather
    than a naive positional zip that silently misaligns after the first
    calendar mismatch."""
    map_b = dict(dated_returns_b)
    aligned_a: list[Decimal] = []
    aligned_b: list[Decimal] = []
    for d, value_a in dated_returns_a:
        if d in map_b:
            aligned_a.append(value_a)
            aligned_b.append(map_b[d])
    return aligned_a, aligned_b


# ---------------------------------------------------------------------------
# Exposure / turnover / concentration
# ---------------------------------------------------------------------------


def turnover_pct(
    buy_notional: Decimal, sell_notional: Decimal, avg_equity: Decimal
) -> Decimal | None:
    """`min(buys, sells) / avg_equity` — the standard "lesser of
    purchases or sales" turnover convention, which avoids double-
    counting a simple round-trip as 200% turnover."""
    if avg_equity == 0:
        return None
    return (min(buy_notional, sell_notional) / avg_equity) * Decimal(100)


def concentration_hhi(position_weights_pct: list[Decimal]) -> Decimal:
    """Herfindahl-Hirschman index over position weights expressed as
    percentages of equity (0-100) — `sum((w/100)^2)`, ranging from
    `1/n` (perfectly equal-weighted) to `1` (fully concentrated in one
    name). An empty portfolio has an HHI of `0` (no concentration, not
    undefined), a deliberate convention so a flat account doesn't need
    special-casing by every caller."""
    if not position_weights_pct:
        return Decimal(0)
    return sum(((w / Decimal(100)) ** 2 for w in position_weights_pct), Decimal(0))
