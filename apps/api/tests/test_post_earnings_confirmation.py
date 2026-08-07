"""Post-earnings confirmation feature tests (Revision Prompt 5) — the
EPS-surprise sign/denominator edge case (a company estimated to lose
money that beats by losing less), the `CAPABILITY_UNAVAILABLE` vs.
`MISSING_DATA` distinction for intraday-dependent components, guidance's
explicit `NONE_PROVIDED` outcome, and reversal/failed-breakout
detection from daily open/close alone."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tradingos_api.services.post_earnings_confirmation import compute_post_earnings_confirmation


def _base_kwargs() -> dict[str, Any]:
    return {
        "actual_eps": Decimal("1.10"),
        "estimate_eps": Decimal("1.00"),
        "actual_revenue": Decimal("5_100_000_000"),
        "estimate_revenue": Decimal("5_000_000_000"),
        "new_guidance_midpoint": Decimal("1.20"),
        "prior_guidance_midpoint": Decimal("1.10"),
        "consensus_midpoint": Decimal("1.15"),
        "gap_pct": Decimal("3.5"),
        "session_open": Decimal("103.5"),
        "session_close": Decimal("106.0"),
        "has_intraday_capability": False,
        "range_30min_pct": None,
        "range_60min_pct": None,
        "price_vs_vwap_pct": None,
        "day_volume": 12_000_000,
        "baseline_avg_volume": 8_000_000,
        "instrument_return_pct": Decimal("3.0"),
        "sector_return_pct": Decimal("1.5"),
        "market_return_pct": Decimal("0.8"),
    }


class TestEpsSurpriseSignAndDenominatorHandling:
    def test_beat_estimate_is_pass_with_positive_surprise(self) -> None:
        kwargs = _base_kwargs()
        result = compute_post_earnings_confirmation(**kwargs)
        eps = next(c for c in result.components if c.component_key == "EPS_SURPRISE")
        assert eps.status == "PASS"
        assert eps.value == Decimal("10.0")  # (1.10 - 1.00) / |1.00| * 100

    def test_negative_estimate_beaten_by_losing_less_is_a_positive_surprise(self) -> None:
        """The classic sign bug: with a signed denominator,
        `(actual - estimate) / estimate` for `estimate=-1.00,
        actual=-0.50` (losing less than expected — a real beat) would
        divide by a negative number and come out negative. Dividing by
        `abs(estimate)` fixes this."""
        kwargs = _base_kwargs()
        kwargs["actual_eps"] = Decimal("-0.50")
        kwargs["estimate_eps"] = Decimal("-1.00")
        result = compute_post_earnings_confirmation(**kwargs)
        eps = next(c for c in result.components if c.component_key == "EPS_SURPRISE")
        assert eps.status == "PASS"
        assert eps.value == Decimal("50.0")  # (-0.50 - -1.00) / |-1.00| * 100 = +50%

    def test_zero_estimate_reports_missing_data_not_a_divide_by_zero(self) -> None:
        kwargs = _base_kwargs()
        kwargs["estimate_eps"] = Decimal("0")
        result = compute_post_earnings_confirmation(**kwargs)
        eps = next(c for c in result.components if c.component_key == "EPS_SURPRISE")
        assert eps.status == "MISSING_DATA"


class TestGuidanceDirection:
    def test_no_guidance_provided_is_its_own_explicit_outcome(self) -> None:
        kwargs = _base_kwargs()
        kwargs["new_guidance_midpoint"] = None
        result = compute_post_earnings_confirmation(**kwargs)
        guidance = next(c for c in result.components if c.component_key == "GUIDANCE_DIRECTION")
        assert guidance.status == "MISSING_DATA"
        assert guidance.detail == "NONE_PROVIDED"

    def test_guidance_below_prior_is_lowered_and_fails(self) -> None:
        kwargs = _base_kwargs()
        kwargs["new_guidance_midpoint"] = Decimal("1.00")
        result = compute_post_earnings_confirmation(**kwargs)
        guidance = next(c for c in result.components if c.component_key == "GUIDANCE_DIRECTION")
        assert guidance.status == "FAIL"
        assert guidance.detail == "LOWERED"


class TestCapabilityUnavailableForIntradayComponents:
    def test_no_intraday_capability_marks_30_and_60_minute_range_and_vwap_capability_unavailable(
        self,
    ) -> None:
        kwargs = _base_kwargs()
        kwargs["has_intraday_capability"] = False
        result = compute_post_earnings_confirmation(**kwargs)
        by_key = {c.component_key: c.status for c in result.components}
        assert by_key["FIRST_30MIN_RANGE"] == "CAPABILITY_UNAVAILABLE"
        assert by_key["FIRST_60MIN_RANGE"] == "CAPABILITY_UNAVAILABLE"
        assert by_key["VWAP_HOLD"] == "CAPABILITY_UNAVAILABLE"

    def test_capability_present_but_value_missing_today_is_missing_data_not_unavailable(
        self,
    ) -> None:
        kwargs = _base_kwargs()
        kwargs["has_intraday_capability"] = True
        kwargs["range_30min_pct"] = None
        result = compute_post_earnings_confirmation(**kwargs)
        range_30 = next(c for c in result.components if c.component_key == "FIRST_30MIN_RANGE")
        assert range_30.status == "MISSING_DATA"

    def test_capability_present_and_value_supplied_passes_when_positive(self) -> None:
        kwargs = _base_kwargs()
        kwargs["has_intraday_capability"] = True
        kwargs["range_30min_pct"] = Decimal("1.5")
        kwargs["range_60min_pct"] = Decimal("2.1")
        kwargs["price_vs_vwap_pct"] = Decimal("0.4")
        result = compute_post_earnings_confirmation(**kwargs)
        by_key = {c.component_key: c.status for c in result.components}
        assert by_key["FIRST_30MIN_RANGE"] == "PASS"
        assert by_key["FIRST_60MIN_RANGE"] == "PASS"
        assert by_key["VWAP_HOLD"] == "PASS"


class TestReversalAndFailedBreakout:
    def test_gap_up_closing_below_open_is_flagged_as_a_reversal(self) -> None:
        kwargs = _base_kwargs()
        kwargs["gap_pct"] = Decimal("3.0")
        kwargs["session_open"] = Decimal("103.0")
        kwargs["session_close"] = Decimal("99.0")
        result = compute_post_earnings_confirmation(**kwargs)
        reversal = next(
            c for c in result.components if c.component_key == "REVERSAL_FAILED_BREAKOUT"
        )
        assert reversal.status == "FAIL"
        assert reversal.detail == "gap reversed intraday"

    def test_gap_up_closing_higher_is_confirmed_no_reversal(self) -> None:
        kwargs = _base_kwargs()
        result = compute_post_earnings_confirmation(**kwargs)
        reversal = next(
            c for c in result.components if c.component_key == "REVERSAL_FAILED_BREAKOUT"
        )
        assert reversal.status == "PASS"
        assert reversal.detail is None


class TestGates:
    def test_all_gates_pass_for_a_clean_beat_and_raise(self) -> None:
        result = compute_post_earnings_confirmation(**_base_kwargs())
        assert result.results_gate_passed is True
        assert result.guidance_gate_passed is True
        assert result.market_reaction_gate_passed is True
        assert result.all_gates_passed is True

    def test_results_gate_fails_independently_of_guidance_and_market_gates(self) -> None:
        kwargs = _base_kwargs()
        kwargs["actual_eps"] = Decimal("0.90")  # miss
        result = compute_post_earnings_confirmation(**kwargs)
        assert result.results_gate_passed is False
        assert result.guidance_gate_passed is True
        assert result.market_reaction_gate_passed is True
        assert result.all_gates_passed is False
