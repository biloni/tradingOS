"""compute_score is a pure function over plain Decimal/dict inputs (no DB),
so it's tested against hand-computed invariants — same discipline as
services/indicators.py's tests (see that module's test file docstring)."""

from decimal import Decimal

from tradingos_api.models.recommendation import RecommendationConfidence
from tradingos_api.services.scoring import compute_score
from tradingos_api.services.strategy import DEFAULT_CONFIG


def _indicators(**overrides: Decimal) -> dict[str, Decimal]:
    return overrides


class TestAllSignalsAgree:
    def test_all_bullish_scores_100_and_high_confidence(self) -> None:
        result = compute_score(
            close=Decimal("105"),
            indicators=_indicators(
                SMA_20=Decimal("110"),
                SMA_50=Decimal("100"),
                RSI_14=Decimal("60"),
                MACD_LINE=Decimal("2"),
                MACD_SIGNAL=Decimal("1"),
                BB_MID=Decimal("100"),
            ),
            config=DEFAULT_CONFIG,
        )
        assert result.score == Decimal(100)
        assert result.confidence == RecommendationConfidence.HIGH
        assert all(v == 1 for v in result.signal_breakdown.values())

    def test_all_bearish_scores_0_and_high_confidence(self) -> None:
        result = compute_score(
            close=Decimal("95"),
            indicators=_indicators(
                SMA_20=Decimal("90"),
                SMA_50=Decimal("100"),
                RSI_14=Decimal("20"),
                MACD_LINE=Decimal("1"),
                MACD_SIGNAL=Decimal("2"),
                BB_MID=Decimal("100"),
            ),
            config=DEFAULT_CONFIG,
        )
        assert result.score == Decimal(0)
        assert result.confidence == RecommendationConfidence.HIGH
        assert all(v == -1 for v in result.signal_breakdown.values())


class TestMixedSignals:
    def test_two_versus_two_ties_at_50_and_low_confidence(self) -> None:
        result = compute_score(
            close=Decimal("95"),  # bollinger: bearish (close < BB_MID)
            indicators=_indicators(
                SMA_20=Decimal("110"),
                SMA_50=Decimal("100"),  # trend: bullish
                RSI_14=Decimal("20"),  # momentum: bearish (oversold)
                MACD_LINE=Decimal("2"),
                MACD_SIGNAL=Decimal("1"),  # macd: bullish
                BB_MID=Decimal("100"),
            ),
            config=DEFAULT_CONFIG,
        )
        assert result.score == Decimal(50)
        assert result.confidence == RecommendationConfidence.LOW

    def test_three_versus_one_is_medium_not_high(self) -> None:
        """3-bullish-1-bearish has real disagreement (net = 2), unlike
        3-bullish-1-neutral (net = 3, HIGH) — see
        services/scoring.py's `_confidence_from_signals` docstring."""
        result = compute_score(
            close=Decimal("95"),  # bollinger: bearish
            indicators=_indicators(
                SMA_20=Decimal("110"),
                SMA_50=Decimal("100"),  # trend: bullish
                RSI_14=Decimal("60"),  # momentum: bullish
                MACD_LINE=Decimal("2"),
                MACD_SIGNAL=Decimal("1"),  # macd: bullish
                BB_MID=Decimal("100"),
            ),
            config=DEFAULT_CONFIG,
        )
        assert result.score == Decimal(75)
        assert result.confidence == RecommendationConfidence.MEDIUM

    def test_three_bullish_one_neutral_is_high(self) -> None:
        result = compute_score(
            close=Decimal("100"),  # bollinger: neutral (close == BB_MID)
            indicators=_indicators(
                SMA_20=Decimal("110"),
                SMA_50=Decimal("100"),  # trend: bullish
                RSI_14=Decimal("60"),  # momentum: bullish
                MACD_LINE=Decimal("2"),
                MACD_SIGNAL=Decimal("1"),  # macd: bullish
                BB_MID=Decimal("100"),
            ),
            config=DEFAULT_CONFIG,
        )
        assert result.confidence == RecommendationConfidence.HIGH


class TestMissingData:
    def test_no_indicators_at_all_scores_50_and_low_confidence(self) -> None:
        result = compute_score(close=None, indicators={}, config=DEFAULT_CONFIG)
        assert result.score == Decimal(50)
        assert result.confidence == RecommendationConfidence.LOW
        assert all(v == 0 for v in result.signal_breakdown.values())
