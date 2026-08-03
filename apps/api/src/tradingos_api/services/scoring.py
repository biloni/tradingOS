"""Deterministic swing-trade candidate scoring (principle 6: plain code, no
LLM involvement — the LLM only explains this score, never computes or
overrides it, per docs/MODEL_GOVERNANCE.md).

Combines four Phase 2 indicators into one 0-100 "bullish alignment" score:
trend (SMA_20 vs SMA_50), momentum (RSI_14 band), MACD crossover state, and
Bollinger-band position (close vs BB_MID). Weights/thresholds come from the
active `StrategyVersion.config` (JSON) — never hardcoded (principle 8).

Confidence is a deterministic qualitative band (LOW/MEDIUM/HIGH), computed
from how many signals *agree* net of how many *disagree* — never the LLM's
self-reported confidence (principle 15; see docs/MODEL_GOVERNANCE.md).
"""

from decimal import Decimal
from typing import Any

from tradingos_api.models.recommendation import RecommendationConfidence


class ScoreResult:
    def __init__(
        self,
        score: Decimal,
        confidence: RecommendationConfidence,
        signal_breakdown: dict[str, int],
    ) -> None:
        self.score = score
        self.confidence = confidence
        self.signal_breakdown = signal_breakdown


def _trend_signal(sma_20: Decimal | None, sma_50: Decimal | None) -> int:
    if sma_20 is None or sma_50 is None:
        return 0
    if sma_20 > sma_50:
        return 1
    if sma_20 < sma_50:
        return -1
    return 0


def _momentum_signal(rsi_14: Decimal | None, config: dict[str, Any]) -> int:
    if rsi_14 is None:
        return 0
    low = Decimal(str(config.get("rsi_bullish_low", 50)))
    high = Decimal(str(config.get("rsi_bullish_high", 70)))
    oversold = Decimal(str(config.get("rsi_oversold", 30)))
    if low <= rsi_14 <= high:
        return 1
    if rsi_14 < oversold:
        return -1
    return 0


def _macd_crossover_signal(macd_line: Decimal | None, macd_signal: Decimal | None) -> int:
    if macd_line is None or macd_signal is None:
        return 0
    if macd_line > macd_signal:
        return 1
    if macd_line < macd_signal:
        return -1
    return 0


def _bollinger_signal(close: Decimal | None, bb_mid: Decimal | None) -> int:
    if close is None or bb_mid is None:
        return 0
    if close > bb_mid:
        return 1
    if close < bb_mid:
        return -1
    return 0


def _confidence_from_signals(signals: dict[str, int]) -> RecommendationConfidence:
    """HIGH requires near-unanimous agreement (net >= 3 of 4); a signal that
    actively disagrees (not just neutral) caps confidence lower even if the
    majority agrees — e.g. 3-bullish-1-neutral is HIGH, but
    3-bullish-1-bearish is only MEDIUM, since there IS real disagreement."""
    bullish = sum(1 for v in signals.values() if v > 0)
    bearish = sum(1 for v in signals.values() if v < 0)
    net = abs(bullish - bearish)
    if net >= 3:
        return RecommendationConfidence.HIGH
    if net == 2:
        return RecommendationConfidence.MEDIUM
    return RecommendationConfidence.LOW


def compute_score(
    close: Decimal | None,
    indicators: dict[str, Decimal],
    config: dict[str, Any],
) -> ScoreResult:
    """`indicators` is keyed by `IndicatorName` value strings (e.g.
    "SMA_20") — the same shape `GET /api/v1/symbols/{ticker}/indicators`
    already returns, so callers can pass that straight through."""
    signals = {
        "trend": _trend_signal(indicators.get("SMA_20"), indicators.get("SMA_50")),
        "momentum": _momentum_signal(indicators.get("RSI_14"), config),
        "macd": _macd_crossover_signal(indicators.get("MACD_LINE"), indicators.get("MACD_SIGNAL")),
        "bollinger": _bollinger_signal(close, indicators.get("BB_MID")),
    }

    weights_config = config.get("weights", {})
    weights = {
        name: Decimal(str(weights_config.get(name, 1.0)))
        if isinstance(weights_config, dict)
        else Decimal("1.0")
        for name in signals
    }

    weighted_sum = sum((Decimal(signals[name]) * weights[name] for name in signals), Decimal(0))
    max_weight = sum(weights.values(), Decimal(0))
    if max_weight == 0:
        score = Decimal(50)
    else:
        score = Decimal(50) + (weighted_sum / max_weight) * Decimal(50)

    return ScoreResult(
        score=score,
        confidence=_confidence_from_signals(signals),
        signal_breakdown=signals,
    )
