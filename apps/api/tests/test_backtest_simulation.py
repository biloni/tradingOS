"""Pure-core backtest simulation tests — hand-authored fixtures, no DB, no
ORM (see services/backtest.py's module docstring for the split rationale).
Same discipline as test_indicators.py/test_scoring.py: hand-verifiable
invariants over small, fully-controlled series."""

from datetime import date, timedelta
from decimal import Decimal

from tradingos_api.services.backtest import (
    BacktestParams,
    SymbolBar,
    SymbolSeries,
    Trade,
    compute_buy_and_hold_return_pct,
    run_backtest_simulation,
)

D0 = date(2026, 1, 1)


def _dates(n: int) -> list[date]:
    return [D0 + timedelta(days=i) for i in range(n)]


def _signal_indicators(
    close: Decimal, trend: int = 0, momentum: int = 0, macd: int = 0, bollinger: int = 0
) -> dict[str, Decimal]:
    """Builds an indicator dict producing an exact net signal count (each
    of the 4 args is -1/0/1). `bollinger` is relative to `close` (which
    must equal the corresponding bar's actual close) so a "neutral" day
    can still have a moving price without accidentally tripping a
    bollinger signal."""
    sma: dict[int, tuple[Decimal, Decimal]] = {
        1: (Decimal(110), Decimal(100)),
        -1: (Decimal(90), Decimal(100)),
        0: (Decimal(100), Decimal(100)),
    }
    rsi: dict[int, Decimal] = {1: Decimal(60), -1: Decimal(20), 0: Decimal(40)}
    macd_vals: dict[int, tuple[Decimal, Decimal]] = {
        1: (Decimal(2), Decimal(1)),
        -1: (Decimal(1), Decimal(2)),
        0: (Decimal(1), Decimal(1)),
    }
    bb_mid: dict[int, Decimal] = {1: close - Decimal(5), -1: close + Decimal(5), 0: close}

    sma_20, sma_50 = sma[trend]
    macd_line, macd_signal = macd_vals[macd]
    return {
        "SMA_20": sma_20,
        "SMA_50": sma_50,
        "RSI_14": rsi[momentum],
        "MACD_LINE": macd_line,
        "MACD_SIGNAL": macd_signal,
        "BB_MID": bb_mid[bollinger],
    }


def _series(
    ticker: str, bars: list[SymbolBar], indicators: dict[date, dict[str, Decimal]]
) -> SymbolSeries:
    return SymbolSeries(ticker=ticker, symbol_id=1, bars=bars, indicators_by_date=indicators)


class TestFillTiming:
    def test_entry_signal_fills_at_next_days_open_not_same_day_close(self) -> None:
        dates = _dates(4)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(100), close=Decimal(100)),
            SymbolBar(as_of=dates[1], open=Decimal(102), close=Decimal(105)),  # bullish signal day
            SymbolBar(as_of=dates[2], open=Decimal(110), close=Decimal(100)),  # fill happens here
            SymbolBar(as_of=dates[3], open=Decimal(101), close=Decimal(100)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(100)),
            dates[1]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            dates[2]: _signal_indicators(Decimal(100)),
            dates[3]: _signal_indicators(Decimal(100)),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(dates, {"TEST": series}, {}, BacktestParams())

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_date == dates[2]
        assert trade.entry_price == Decimal(110)

    def test_signal_on_last_bar_is_dropped_not_executed(self) -> None:
        dates = _dates(2)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(100), close=Decimal(100)),
            SymbolBar(as_of=dates[1], open=Decimal(101), close=Decimal(105)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(100)),
            dates[1]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(dates, {"TEST": series}, {}, BacktestParams())

        assert result.trades == []
        assert result.num_trades == 0


class TestExitConditions:
    def test_max_holding_days_forces_exit_when_no_signal_exit_fires(self) -> None:
        dates = _dates(6)
        bars = [
            SymbolBar(as_of=dates[i], open=Decimal(100 + i), close=Decimal(100)) for i in range(6)
        ]
        indicators = {d: _signal_indicators(Decimal(100)) for d in dates}
        indicators[dates[1]] = _signal_indicators(
            Decimal(100), trend=1, momentum=1, macd=1, bollinger=1
        )
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(
            dates, {"TEST": series}, {}, BacktestParams(max_holding_days=2)
        )

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_date == dates[2]
        assert trade.entry_price == Decimal(102)
        assert trade.exit_date == dates[5]
        assert trade.exit_price == Decimal(105)
        assert trade.exit_reason == "MAX_HOLDING_DAYS"

    def test_end_of_window_force_closes_open_position_with_correct_reason(self) -> None:
        dates = _dates(4)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(100), close=Decimal(105)),
            SymbolBar(as_of=dates[1], open=Decimal(101), close=Decimal(100)),
            SymbolBar(as_of=dates[2], open=Decimal(102), close=Decimal(100)),
            SymbolBar(as_of=dates[3], open=Decimal(103), close=Decimal(100)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            dates[1]: _signal_indicators(Decimal(100)),
            dates[2]: _signal_indicators(Decimal(100)),
            dates[3]: _signal_indicators(Decimal(100)),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(
            dates, {"TEST": series}, {}, BacktestParams(max_holding_days=100)
        )

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_date == dates[1]
        assert trade.entry_price == Decimal(101)
        assert trade.exit_date == dates[3]
        assert trade.exit_price == Decimal(100)
        assert trade.exit_reason == "END_OF_BACKTEST"


class TestNoPyramiding:
    def test_repeated_bullish_signal_while_holding_does_not_open_a_second_position(self) -> None:
        dates = _dates(5)
        bars = [SymbolBar(as_of=d, open=Decimal(100), close=Decimal(105)) for d in dates]
        bullish = _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1)
        indicators = dict.fromkeys(dates, bullish)
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(dates, {"TEST": series}, {}, BacktestParams())

        assert result.num_trades == 1
        assert result.trades[0].quantity == result.trades[-1].quantity


class TestPositionSizing:
    def test_whole_share_flooring_and_cash_cap(self) -> None:
        dates = _dates(3)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(30), close=Decimal(105)),
            SymbolBar(as_of=dates[1], open=Decimal(30), close=Decimal(100)),
            SymbolBar(as_of=dates[2], open=Decimal(30), close=Decimal(100)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            dates[1]: _signal_indicators(Decimal(100)),
            dates[2]: _signal_indicators(Decimal(100)),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(
            dates,
            {"TEST": series},
            {},
            BacktestParams(starting_cash=Decimal("1000"), position_size_pct=Decimal("0.10")),
        )

        # budget = min(1000, 1000*0.10) = 100; fill price 30 -> floor(100/30) = 3
        assert result.trades[0].quantity == 3

    def test_entry_skipped_when_budget_buys_less_than_one_share(self) -> None:
        dates = _dates(2)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(150), close=Decimal(105)),
            SymbolBar(as_of=dates[1], open=Decimal(150), close=Decimal(100)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            dates[1]: _signal_indicators(Decimal(100)),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(
            dates,
            {"TEST": series},
            {},
            BacktestParams(starting_cash=Decimal("1000"), position_size_pct=Decimal("0.10")),
        )

        # budget = 100, fill price 150 -> floor(100/150) = 0 -> skipped
        assert result.trades == []


class TestMetrics:
    def test_hand_verified_one_losing_trade(self) -> None:
        dates = _dates(6)
        bars = [
            SymbolBar(as_of=dates[0], open=Decimal(100), close=Decimal(105)),
            SymbolBar(as_of=dates[1], open=Decimal(100), close=Decimal(90)),
            SymbolBar(as_of=dates[2], open=Decimal(100), close=Decimal(80)),
            SymbolBar(as_of=dates[3], open=Decimal(100), close=Decimal(95)),
            SymbolBar(as_of=dates[4], open=Decimal(100), close=Decimal(70)),
            SymbolBar(as_of=dates[5], open=Decimal(70), close=Decimal(70)),
        ]
        indicators = {
            dates[0]: _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            dates[1]: _signal_indicators(Decimal(90)),
            dates[2]: _signal_indicators(Decimal(80)),
            dates[3]: _signal_indicators(Decimal(95)),
            dates[4]: _signal_indicators(Decimal(70), trend=-1, momentum=-1, macd=-1, bollinger=-1),
            dates[5]: _signal_indicators(Decimal(70)),
        }
        series = _series("TEST", bars, indicators)

        result = run_backtest_simulation(
            dates, {"TEST": series}, {}, BacktestParams(starting_cash=Decimal("10000"))
        )

        assert result.num_trades == 1
        trade = result.trades[0]
        assert trade.entry_date == dates[1]
        assert trade.entry_price == Decimal(100)
        assert trade.exit_date == dates[5]
        assert trade.exit_price == Decimal(70)
        assert trade.exit_reason == "SIGNAL_EXIT"
        assert trade.quantity == 10  # floor(1000 budget / 100 fill price)
        assert trade.pnl_usd == Decimal(-300)

        assert result.ending_equity == Decimal(9700)
        assert result.total_return_pct == Decimal(-3)
        assert result.max_drawdown_pct == Decimal(3)
        assert result.win_rate_pct == Decimal(0)
        assert result.avg_win_pct == Decimal(0)
        assert result.avg_loss_pct == Decimal(-30)
        assert result.equity_curve[-1].equity == result.ending_equity


class TestNoLookAhead:
    def test_future_data_never_changes_results_on_or_before_the_boundary_day(self) -> None:
        """The headline no-look-ahead test (docs/TEST_STRATEGY.md's Phase 5
        commitment): run the same shared history once truncated at a
        boundary day, and once extended further with everything *after*
        the boundary deliberately mutated to extreme values. Every
        completed trade and equity-curve point on or before the boundary
        must be identical between the two runs."""
        shared_plan: list[tuple[Decimal, dict[str, Decimal]]] = [
            (Decimal(100), _signal_indicators(Decimal(100))),
            (
                Decimal(105),
                _signal_indicators(Decimal(105), trend=1, momentum=1, macd=1, bollinger=1),
            ),
            (Decimal(100), _signal_indicators(Decimal(100))),
            (
                Decimal(70),
                _signal_indicators(Decimal(70), trend=-1, momentum=-1, macd=-1, bollinger=-1),
            ),
            (Decimal(90), _signal_indicators(Decimal(90))),
            (Decimal(90), _signal_indicators(Decimal(90))),
        ]
        future_plan: list[tuple[Decimal, dict[str, Decimal]]] = [
            (
                Decimal(500),
                _signal_indicators(Decimal(500), trend=1, momentum=1, macd=1, bollinger=1),
            ),
            (
                Decimal(5),
                _signal_indicators(Decimal(5), trend=-1, momentum=-1, macd=-1, bollinger=-1),
            ),
            (
                Decimal(900),
                _signal_indicators(Decimal(900), trend=1, momentum=1, macd=1, bollinger=1),
            ),
            (
                Decimal(1),
                _signal_indicators(Decimal(1), trend=-1, momentum=-1, macd=-1, bollinger=-1),
            ),
        ]

        def _build(
            dates: list[date], plan: list[tuple[Decimal, dict[str, Decimal]]]
        ) -> SymbolSeries:
            bars = [
                SymbolBar(as_of=d, open=c, close=c) for d, (c, _) in zip(dates, plan, strict=True)
            ]
            indicators = {d: ind for d, (_, ind) in zip(dates, plan, strict=True)}
            return _series("TEST", bars, indicators)

        base_dates = _dates(6)
        extended_dates = _dates(10)
        params = BacktestParams()

        short_result = run_backtest_simulation(
            base_dates, {"TEST": _build(base_dates, shared_plan)}, {}, params
        )
        long_result = run_backtest_simulation(
            extended_dates, {"TEST": _build(extended_dates, shared_plan + future_plan)}, {}, params
        )

        boundary_day = base_dates[-1]
        assert short_result.equity_curve == [
            p for p in long_result.equity_curve if p.as_of <= boundary_day
        ]

        def _completed_on_or_before_boundary(trades: list[Trade]) -> list[Trade]:
            return [
                t
                for t in trades
                if t.exit_date <= boundary_day
                and not (t.exit_reason == "END_OF_BACKTEST" and t.exit_date == boundary_day)
            ]

        assert _completed_on_or_before_boundary(
            short_result.trades
        ) == _completed_on_or_before_boundary(long_result.trades)
        # Sanity: the shared plan does produce a real completed trade to compare.
        assert len(_completed_on_or_before_boundary(long_result.trades)) == 1


class TestBuyAndHoldHelper:
    def test_positive_and_negative_returns(self) -> None:
        assert compute_buy_and_hold_return_pct(Decimal(100), Decimal(110)) == Decimal(10)
        assert compute_buy_and_hold_return_pct(Decimal(100), Decimal(90)) == Decimal(-10)

    def test_zero_first_close_is_safe(self) -> None:
        assert compute_buy_and_hold_return_pct(Decimal(0), Decimal(100)) == Decimal(0)


class TestEmptyCalendar:
    def test_empty_trading_calendar_returns_zeroed_result(self) -> None:
        result = run_backtest_simulation([], {}, {}, BacktestParams(starting_cash=Decimal("500")))
        assert result.ending_equity == Decimal("500")
        assert result.num_trades == 0
        assert result.trades == []
        assert result.equity_curve == []
