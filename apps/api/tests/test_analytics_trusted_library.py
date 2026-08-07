"""Compares `services/analytics.py` against the trusted, MIT-licensed
`ta` library (Revision Prompt 5's "compare indicator outputs with an
approved trusted library" requirement). `ta`/`pandas`/`numpy` are dev-
only dependencies — never imported by production code (see
`services/analytics.py`'s own module docstring).

Each indicator's EWM-seeding convention was reverse-engineered from
`ta`'s source directly (documented in `services/analytics.py`): EMA/RSI
recurse from the first observation; ATR is SMA-seeded Wilder smoothing.
Matching each precisely — not assuming one uniform convention — is what
keeps these comparisons tight (<0.001 relative tolerance) rather than
"in the same ballpark."
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange

from tradingos_api.services.analytics import atr, ema, macd, rsi, sma

AS_OF = date(2026, 8, 6)

# A deterministic, non-trivial synthetic close series (no randomness) —
# a gentle uptrend with noise-like wiggles so RSI/MACD aren't degenerate.
_RAW_CLOSES = [
    100.00, 101.20, 100.80, 102.10, 103.00, 102.50, 104.20, 105.00, 104.60, 106.10,
    107.00, 106.40, 108.20, 109.10, 108.70, 110.30, 111.00, 110.50, 112.10, 113.00,
    112.60, 114.20, 115.10, 114.70, 116.30, 117.00, 116.50, 118.10, 119.00, 118.60,
    120.10, 121.00, 120.50, 122.10, 123.00,
]  # fmt: skip

_HIGHS = [c + 0.8 for c in _RAW_CLOSES]
_LOWS = [c - 0.8 for c in _RAW_CLOSES]

_RELATIVE_TOLERANCE = Decimal("0.001")


def _closes_decimal() -> list[Decimal | None]:
    return [Decimal(str(c)) for c in _RAW_CLOSES]


def _assert_close(ours: Decimal, theirs: float, *, label: str) -> None:
    theirs_dec = Decimal(str(theirs))
    if theirs_dec == 0:
        assert abs(ours) < Decimal("0.01"), f"{label}: ours={ours} theirs={theirs_dec}"
        return
    relative_diff = abs(ours - theirs_dec) / abs(theirs_dec)
    assert relative_diff < _RELATIVE_TOLERANCE, (
        f"{label}: ours={ours} theirs={theirs_dec} relative_diff={relative_diff}"
    )


@pytest.fixture(scope="module")
def price_series() -> pd.Series:
    return pd.Series(_RAW_CLOSES)


class TestSmaMatchesTrustedLibrary:
    def test_sma_20_matches_ta(self, price_series: pd.Series) -> None:
        ours = sma(_closes_decimal(), 20, AS_OF)
        theirs = SMAIndicator(price_series, window=20).sma_indicator().iloc[-1]
        assert ours.status == "OK" and ours.value is not None
        _assert_close(ours.value, theirs, label="SMA")


class TestEmaMatchesTrustedLibrary:
    def test_ema_20_matches_ta(self, price_series: pd.Series) -> None:
        ours = ema(_closes_decimal(), 20, AS_OF)
        theirs = EMAIndicator(price_series, window=20).ema_indicator().iloc[-1]
        assert ours.status == "OK" and ours.value is not None
        _assert_close(ours.value, theirs, label="EMA")


class TestRsiMatchesTrustedLibrary:
    def test_rsi_14_matches_ta(self, price_series: pd.Series) -> None:
        ours = rsi(_closes_decimal(), 14, AS_OF)
        theirs = RSIIndicator(price_series, window=14).rsi().iloc[-1]
        assert ours.status == "OK" and ours.value is not None
        _assert_close(ours.value, theirs, label="RSI")


class TestMacdMatchesTrustedLibrary:
    def test_macd_line_and_signal_match_ta(self, price_series: pd.Series) -> None:
        ours = macd(_closes_decimal(), AS_OF)
        ta_macd = MACD(price_series, window_fast=12, window_slow=26, window_sign=9)
        assert ours.macd_line.status == "OK" and ours.macd_line.value is not None
        assert ours.signal_line.status == "OK" and ours.signal_line.value is not None
        _assert_close(ours.macd_line.value, ta_macd.macd().iloc[-1], label="MACD_LINE")
        _assert_close(ours.signal_line.value, ta_macd.macd_signal().iloc[-1], label="MACD_SIGNAL")


class TestAtrMatchesTrustedLibrary:
    def test_atr_14_matches_ta(self) -> None:
        highs = pd.Series(_HIGHS)
        lows = pd.Series(_LOWS)
        closes = pd.Series(_RAW_CLOSES)
        ours = atr(
            [Decimal(str(h)) for h in _HIGHS],
            [Decimal(str(low)) for low in _LOWS],
            _closes_decimal(),
            14,
            AS_OF,
        )
        theirs = AverageTrueRange(highs, lows, closes, window=14).average_true_range().iloc[-1]
        assert ours.status == "OK" and ours.value is not None
        _assert_close(ours.value, theirs, label="ATR")
