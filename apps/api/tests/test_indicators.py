"""Indicator tests use hand-verifiable invariants and hand-computed small
series — not half-remembered "textbook" reference numbers that could be
misremembered and would then validate nothing (see services/indicators.py
module docstring)."""

from decimal import Decimal

from tradingos_api.services.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)


def _decimals(values: list[int]) -> list[Decimal]:
    return [Decimal(v) for v in values]


class TestSma:
    def test_constant_series_equals_the_constant(self) -> None:
        closes = _decimals([50] * 10)
        result = sma(closes, window=5)
        assert result[:4] == [None, None, None, None]
        assert all(v == Decimal(50) for v in result[4:])

    def test_hand_computed_ascending_series(self) -> None:
        closes = _decimals([1, 2, 3, 4, 5])
        result = sma(closes, window=3)
        assert result == [None, None, Decimal(2), Decimal(3), Decimal(4)]


class TestEma:
    def test_constant_series_equals_the_constant(self) -> None:
        closes = _decimals([50] * 10)
        result = ema(closes, span=5)
        assert result[:4] == [None, None, None, None]
        assert all(v == Decimal(50) for v in result[4:])

    def test_hand_computed_ascending_series(self) -> None:
        # alpha = 2/(3+1) = 0.5; raw = [1, 1.5, 2.25, 3.125, 4.0625]
        closes = _decimals([1, 2, 3, 4, 5])
        result = ema(closes, span=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == Decimal("2.25")
        assert result[3] == Decimal("3.125")
        assert result[4] == Decimal("4.0625")


class TestRsi:
    def test_all_gains_approaches_100(self) -> None:
        closes = _decimals(list(range(1, 21)))  # strictly increasing
        result = rsi(closes, period=14)
        for value in result[14:]:
            assert value == Decimal(100)

    def test_all_losses_approaches_0(self) -> None:
        closes = _decimals(list(range(20, 0, -1)))  # strictly decreasing
        result = rsi(closes, period=14)
        for value in result[14:]:
            assert value == Decimal(0)

    def test_flat_series_is_50_by_explicit_convention(self) -> None:
        closes = _decimals([100] * 20)
        result = rsi(closes, period=14)
        for value in result[14:]:
            assert value == Decimal(50)

    def test_none_before_enough_history(self) -> None:
        closes = _decimals([100] * 10)
        result = rsi(closes, period=14)
        assert all(v is None for v in result)


class TestMacd:
    def test_constant_series_line_signal_histogram_are_all_zero(self) -> None:
        closes = _decimals([50] * 40)
        result = macd(closes, fast=12, slow=26, signal_span=9)
        # unmasked from index 26-1+9-1 = 33 onward for signal/histogram
        assert all(v == Decimal(0) for v in result.line[25:])
        assert all(v == Decimal(0) for v in result.signal[33:])
        assert all(v == Decimal(0) for v in result.histogram[33:])
        assert result.line[24] is None
        assert result.signal[32] is None


class TestBollingerBands:
    def test_constant_series_bands_collapse_to_the_constant(self) -> None:
        closes = _decimals([50] * 25)
        result = bollinger_bands(closes, window=20, num_std=2)
        for value in result.upper[19:]:
            assert value == Decimal(50)
        for value in result.lower[19:]:
            assert value == Decimal(50)

    def test_mid_band_equals_sma(self) -> None:
        closes = _decimals([1, 2, 3, 4, 5, 6, 7, 8])
        result = bollinger_bands(closes, window=3, num_std=2)
        assert result.mid == sma(closes, window=3)


class TestAtr:
    def test_zero_volatility_series_is_zero(self) -> None:
        closes = _decimals([100] * 20)
        result = atr(highs=closes, lows=closes, closes=closes, period=14)
        assert result[:13] == [None] * 13
        assert all(v == Decimal(0) for v in result[13:])

    def test_none_before_enough_history(self) -> None:
        closes = _decimals([100] * 10)
        result = atr(highs=closes, lows=closes, closes=closes, period=14)
        assert all(v is None for v in result)
