"""Gap-through-stop tests (Revision Prompt 7, HES-5) — the required
"gap-through-stop" scenario and "a stop order is never represented as a
guarantee of the stop price" (checked as a literal, always-present
substring in the disclosure text, not just a design intent)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingos_api.services.gap_risk import estimate_stop_fill_under_gap


class TestGapThroughStop:
    def test_adverse_gap_carries_price_through_a_sell_stop(self) -> None:
        """A long position's protective sell-stop at $95, prior close
        $100, and a -8% overnight gap: the implied open ($92) is below
        the stop, so the estimated fill is the gapped-open price, not
        the $95 stop price — a real, material difference."""
        estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("95.00"),
            prior_close=Decimal("100.00"),
            gap_pct=Decimal("-8.0"),
            side="SELL_STOP",
        )
        assert estimate.gapped_through_stop is True
        assert estimate.implied_open == Decimal("92.00")
        assert estimate.estimated_fill_price == Decimal("92.00")
        assert estimate.slippage_vs_stop == Decimal("3.00")

    def test_small_gap_does_not_carry_through_the_stop(self) -> None:
        estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("95.00"),
            prior_close=Decimal("100.00"),
            gap_pct=Decimal("-1.0"),
            side="SELL_STOP",
        )
        assert estimate.gapped_through_stop is False
        assert estimate.estimated_fill_price == Decimal("95.00")
        assert estimate.slippage_vs_stop == Decimal("0")

    def test_buy_stop_gapping_upward_through_its_trigger(self) -> None:
        estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("105.00"),
            prior_close=Decimal("100.00"),
            gap_pct=Decimal("8.0"),
            side="BUY_STOP",
        )
        assert estimate.gapped_through_stop is True
        assert estimate.implied_open == Decimal("108.00")
        assert estimate.estimated_fill_price == Decimal("108.00")
        assert estimate.slippage_vs_stop == Decimal("3.00")


class TestStopNeverRepresentedAsAGuarantee:
    def test_disclosure_states_not_a_guarantee_even_when_the_stop_holds(self) -> None:
        estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("95.00"),
            prior_close=Decimal("100.00"),
            gap_pct=Decimal("-0.1"),
            side="SELL_STOP",
        )
        assert estimate.gapped_through_stop is False
        assert "NOT a guaranteed execution price" in estimate.disclosure

    def test_disclosure_states_not_a_guarantee_when_the_stop_is_breached(self) -> None:
        estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("95.00"),
            prior_close=Decimal("100.00"),
            gap_pct=Decimal("-8.0"),
            side="SELL_STOP",
        )
        assert "NOT a guaranteed execution price" in estimate.disclosure
        assert "materially" in estimate.disclosure.lower() or "worse" in estimate.disclosure.lower()


class TestInputValidation:
    def test_non_positive_prior_close_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="prior_close"):
            estimate_stop_fill_under_gap(
                stop_price=Decimal("95.00"), prior_close=Decimal("0"), gap_pct=Decimal("-1.0")
            )

    def test_non_positive_stop_price_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="stop_price"):
            estimate_stop_fill_under_gap(
                stop_price=Decimal("0"), prior_close=Decimal("100.00"), gap_pct=Decimal("-1.0")
            )
