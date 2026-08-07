"""Market regime classification tests (Revision Prompt 5, ADR-034) —
STRESSED/CALM/ELEVATED cases and the "mixed/incomplete signals default
to the conservative middle state, never silently CALM" rule."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingos_api.services.market_regime import classify_market_regime

AS_OF = date(2026, 8, 6)


def _uptrend(n: int, start: Decimal) -> list[Decimal | None]:
    return [start + Decimal(i) * Decimal("0.5") for i in range(n)]


def _downtrend(n: int, start: Decimal) -> list[Decimal | None]:
    return [start - Decimal(i) * Decimal("0.5") for i in range(n)]


class TestCalmRegime:
    def test_low_vix_percentile_and_spy_uptrend_is_calm(self) -> None:
        vix_history = [Decimal(15) + Decimal(i) * Decimal("0.1") for i in range(60)]  # low, stable
        result = classify_market_regime(
            spy_closes=_uptrend(60, Decimal(400)),
            qqq_closes=_uptrend(60, Decimal(350)),
            vix_proxy_closes=vix_history + [Decimal(10)],  # ends below its own history
            breadth_pct_above_sma50=Decimal(65),
            as_of=AS_OF,
        )
        assert result.classification == "CALM"


class TestStressedRegime:
    def test_high_vix_percentile_alone_is_stressed(self) -> None:
        vix_history = [Decimal(15) for _ in range(60)]
        result = classify_market_regime(
            spy_closes=_uptrend(60, Decimal(400)),
            qqq_closes=_uptrend(60, Decimal(350)),
            vix_proxy_closes=vix_history + [Decimal(45)],  # far above its own history
            breadth_pct_above_sma50=Decimal(50),
            as_of=AS_OF,
        )
        assert result.classification == "STRESSED"
        assert "VIX" in result.explanation_code

    def test_both_spy_and_qqq_downtrend_is_stressed_even_without_vix_data(self) -> None:
        result = classify_market_regime(
            spy_closes=_downtrend(60, Decimal(400)),
            qqq_closes=_downtrend(60, Decimal(350)),
            vix_proxy_closes=[],
            breadth_pct_above_sma50=None,
            as_of=AS_OF,
        )
        assert result.classification == "STRESSED"
        assert "downtrend" in result.explanation_code


class TestElevatedIsTheConservativeDefault:
    def test_missing_vix_and_mixed_trend_defaults_to_elevated_not_calm(self) -> None:
        result = classify_market_regime(
            spy_closes=_uptrend(60, Decimal(400)),
            qqq_closes=_downtrend(60, Decimal(350)),  # mixed signal
            vix_proxy_closes=[],  # no VIX data at all
            breadth_pct_above_sma50=None,
            as_of=AS_OF,
        )
        assert result.classification == "ELEVATED"
        assert "mixed or incomplete" in result.explanation_code

    def test_elevated_realized_volatility_overrides_an_otherwise_calm_read(self) -> None:
        # Sharp daily swings drive realized volatility above the 30%
        # threshold even though the trend itself is technically up.
        volatile_closes: list[Decimal | None] = []
        price = Decimal(400)
        for i in range(60):
            price = price + (Decimal(20) if i % 2 == 0 else Decimal(-18))
            volatile_closes.append(price)
        result = classify_market_regime(
            spy_closes=volatile_closes,
            qqq_closes=volatile_closes,
            vix_proxy_closes=[],
            breadth_pct_above_sma50=None,
            as_of=AS_OF,
        )
        assert result.classification == "ELEVATED"
        assert "volatility" in result.explanation_code
