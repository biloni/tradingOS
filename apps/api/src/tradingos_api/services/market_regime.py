"""Deterministic market-regime classification (Revision Prompt 5,
ADR-034). Feeds `models.market_evidence.MarketRegimeSnapshot` — a risk-
budget input only, never an independent buy/sell trigger (ADR-034's own
constraint, unchanged). Every threshold below is a versioned constant in
this module (`CALCULATION_VERSION`), not a magic number buried in a
conditional — principle 8.

Deliberately conservative when signals are missing or mixed: `ELEVATED`
is the default middle state, never silently defaulted to `CALM`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tradingos_api.services.analytics import IndicatorResult, momentum, realized_volatility, trend

CALCULATION_VERSION = "v1"

# Versioned thresholds (principle 8) — revisit only through the normal
# strategy-change governance loop, never a silent edit.
_VIX_PERCENTILE_STRESSED = Decimal(80)
_VIX_PERCENTILE_CALM = Decimal(40)
_REALIZED_VOL_ELEVATED_PCT = Decimal(30)


@dataclass(frozen=True)
class MarketRegimeResult:
    classification: str
    explanation_code: str
    vix_proxy_level: Decimal | None
    vix_percentile: Decimal | None
    vix_rate_of_change: IndicatorResult | None
    spy_trend: IndicatorResult
    qqq_trend: IndicatorResult
    realized_volatility: IndicatorResult
    breadth_pct_above_sma50: Decimal | None
    calculation_version: str = CALCULATION_VERSION


def _percentile_rank(value: Decimal, history: list[Decimal]) -> Decimal:
    """% of `history` at or below `value` — a simple, documented rank,
    not a parametric distribution fit."""
    if not history:
        return Decimal(50)
    at_or_below = sum(1 for h in history if h <= value)
    return (Decimal(at_or_below) / Decimal(len(history))) * Decimal(100)


def classify_market_regime(
    *,
    spy_closes: list[Decimal | None],
    qqq_closes: list[Decimal | None],
    vix_proxy_closes: list[Decimal | None],
    breadth_pct_above_sma50: Decimal | None,
    as_of: date,
) -> MarketRegimeResult:
    spy_trend = trend(spy_closes, 20, 50, as_of)
    qqq_trend = trend(qqq_closes, 20, 50, as_of)
    vol = realized_volatility(spy_closes, 20, as_of)

    clean_vix = [v for v in vix_proxy_closes if v is not None]
    vix_level = clean_vix[-1] if clean_vix else None
    vix_percentile = (
        _percentile_rank(vix_level, clean_vix[:-1])
        if vix_level is not None and len(clean_vix) > 1
        else None
    )
    vix_roc = None
    if len(vix_proxy_closes) >= 6:
        vix_roc = momentum(vix_proxy_closes, 5, as_of)

    classification, explanation = _classify(
        vix_percentile=vix_percentile,
        spy_trend=spy_trend,
        qqq_trend=qqq_trend,
        realized_vol=vol,
    )

    return MarketRegimeResult(
        classification=classification,
        explanation_code=explanation,
        vix_proxy_level=vix_level,
        vix_percentile=vix_percentile,
        vix_rate_of_change=vix_roc,
        spy_trend=spy_trend,
        qqq_trend=qqq_trend,
        realized_volatility=vol,
        breadth_pct_above_sma50=breadth_pct_above_sma50,
    )


def _classify(
    *,
    vix_percentile: Decimal | None,
    spy_trend: IndicatorResult,
    qqq_trend: IndicatorResult,
    realized_vol: IndicatorResult,
) -> tuple[str, str]:
    if vix_percentile is not None and vix_percentile >= _VIX_PERCENTILE_STRESSED:
        return "STRESSED", "VIX proxy in the top quintile of its trailing history"
    if spy_trend.status == "OK" and qqq_trend.status == "OK":
        if spy_trend.value == Decimal(-1) and qqq_trend.value == Decimal(-1):
            return "STRESSED", "both SPY and QQQ are in a confirmed downtrend"
    if realized_vol.status == "OK" and realized_vol.value is not None:
        if realized_vol.value > _REALIZED_VOL_ELEVATED_PCT:
            return "ELEVATED", f"realized volatility above {_REALIZED_VOL_ELEVATED_PCT}% annualized"
    if (
        vix_percentile is not None
        and vix_percentile <= _VIX_PERCENTILE_CALM
        and spy_trend.status == "OK"
        and spy_trend.value == Decimal(1)
    ):
        return "CALM", "VIX proxy in the bottom two quintiles and SPY in an uptrend"
    return "ELEVATED", "mixed or incomplete signals — defaulting to the conservative middle state"
