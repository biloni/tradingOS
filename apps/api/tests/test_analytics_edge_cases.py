"""Missing-data, insufficient-history, and split-adjustment edge cases
for `services/analytics.py` (Revision Prompt 5's required test
categories). Every indicator must report a structured status rather
than raising or silently returning a wrong number when its input is
short or gappy."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingos_api.services.analytics import atr, ema, macd, relative_strength, rsi, sma

AS_OF = date(2026, 8, 6)


def _closes(n: int, start: Decimal = Decimal(100)) -> list[Decimal | None]:
    return [start + Decimal(i) for i in range(n)]


class TestInsufficientHistory:
    def test_sma_with_fewer_bars_than_window_is_insufficient_history(self) -> None:
        result = sma(_closes(5), 20, AS_OF)
        assert result.status == "INSUFFICIENT_HISTORY"
        assert result.value is None
        assert "20" in (result.explanation_code or "")

    def test_ema_with_fewer_bars_than_window_is_insufficient_history(self) -> None:
        result = ema(_closes(10), 20, AS_OF)
        assert result.status == "INSUFFICIENT_HISTORY"

    def test_rsi_requires_window_plus_one_bars(self) -> None:
        result = rsi(_closes(14), 14, AS_OF)  # needs window + 1 = 15
        assert result.status == "INSUFFICIENT_HISTORY"

    def test_macd_requires_slow_plus_signal_bars(self) -> None:
        result = macd(_closes(20), AS_OF)  # needs 26 + 9 = 35
        assert result.macd_line.status == "INSUFFICIENT_HISTORY"
        assert result.signal_line.status == "INSUFFICIENT_HISTORY"
        assert result.histogram.status == "INSUFFICIENT_HISTORY"

    def test_atr_requires_window_plus_one_bars(self) -> None:
        short = _closes(10)
        result = atr(short, short, short, 14, AS_OF)
        assert result.status == "INSUFFICIENT_HISTORY"

    def test_relative_strength_requires_window_plus_one_bars_on_both_series(self) -> None:
        result = relative_strength(_closes(30), _closes(5), 20, AS_OF)
        assert result.status == "INSUFFICIENT_HISTORY"


class TestMissingDataWithinAnOtherwiseLongEnoughWindow:
    def test_sma_with_a_none_in_the_window_is_missing_data_not_insufficient_history(self) -> None:
        closes = _closes(20)
        closes[-3] = None
        result = sma(closes, 20, AS_OF)
        assert result.status == "MISSING_DATA"

    def test_ema_with_a_none_anywhere_in_the_series_is_missing_data(self) -> None:
        closes = _closes(25)
        closes[0] = None
        result = ema(closes, 20, AS_OF)
        assert result.status == "MISSING_DATA"

    def test_atr_with_a_none_high_is_missing_data(self) -> None:
        closes = _closes(20)
        highs = _closes(20)
        highs[-1] = None
        lows = _closes(20)
        result = atr(highs, lows, closes, 14, AS_OF)
        assert result.status == "MISSING_DATA"


class TestSplitAdjustmentMattersForIndicatorsToo:
    """Mirrors `test_split_adjusted_gaps.py`'s point but for a rolling
    indicator: analytics.py has no split-adjustment logic of its own —
    that is `services/gap_analysis.py` / the ingestion layer's job — so
    feeding it an unadjusted series across a split silently produces a
    nonsensical ATR, which is exactly why the ingestion layer is
    required to split-adjust before any evidence reaches this module."""

    def test_atr_across_an_unadjusted_2_for_1_split_is_dominated_by_the_split_not_real_volatility(
        self,
    ) -> None:
        # 10 stable days at ~200, then an unadjusted 2:1 split drops
        # every subsequent price to ~100 with the same real volatility.
        pre_split = [Decimal("200") + Decimal(i) * Decimal("0.5") for i in range(10)]
        post_split_unadjusted = [Decimal("100") + Decimal(i) * Decimal("0.25") for i in range(10)]
        unadjusted_closes = pre_split + post_split_unadjusted
        unadjusted_highs = [c + Decimal("1") for c in unadjusted_closes]
        unadjusted_lows = [c - Decimal("1") for c in unadjusted_closes]

        result = atr(unadjusted_highs, unadjusted_lows, unadjusted_closes, 14, AS_OF)
        assert result.status == "OK" and result.value is not None
        # Real day-to-day true range here is ~2; the split-day jump
        # alone is ~100, so an ATR anywhere near that magnitude proves
        # the split, not real volatility, dominates the unadjusted read.
        assert result.value > Decimal("5"), (
            "expected the unadjusted split discontinuity to dominate ATR; "
            f"got {result.value}, which would incorrectly look like calm real volatility"
        )
