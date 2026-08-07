"""Baseline eligibility AND-gate tests (Revision Prompt 5) — every
condition must independently pass; one strong condition never
compensates for another's failure, mirroring HES-2's veto philosophy."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tradingos_api.services.baseline_eligibility import evaluate_baseline_eligibility


def _all_passing_kwargs() -> dict[str, Any]:
    return {
        "direction_score": 7,
        "expected_move_pct": Decimal("5.0"),
        "avg_daily_dollar_volume": Decimal("100_000_000"),
        "num_analyst_estimates": 5,
        "timing_category": "AFTER_CLOSE",
        "evidence_is_fresh": True,
        "has_portfolio_capacity": True,
        "has_sector_capacity": True,
        "has_unresolved_data_quality_issue": False,
    }


class TestFullyEligibleEvent:
    def test_all_nine_conditions_pass(self) -> None:
        result = evaluate_baseline_eligibility(**_all_passing_kwargs())
        assert result.eligible is True
        assert all(c.passed for c in result.conditions)
        assert len(result.conditions) == 9


class TestSingleFailingConditionVetoesEligibilityRegardlessOfOthers:
    def test_direction_score_below_six_is_ineligible(self) -> None:
        kwargs = _all_passing_kwargs()
        kwargs["direction_score"] = 5
        result = evaluate_baseline_eligibility(**kwargs)
        assert result.eligible is False
        failing = [c for c in result.conditions if not c.passed]
        assert [c.condition_key for c in failing] == ["DIRECTION_SCORE"]

    def test_expected_move_below_four_percent_is_ineligible(self) -> None:
        kwargs = _all_passing_kwargs()
        kwargs["expected_move_pct"] = Decimal("3.9")
        result = evaluate_baseline_eligibility(**kwargs)
        assert result.eligible is False

    def test_unverified_event_timing_is_ineligible(self) -> None:
        for bad_timing in ("UNKNOWN", "TIME_NOT_SUPPLIED", "DATE_UNCONFIRMED"):
            kwargs = _all_passing_kwargs()
            kwargs["timing_category"] = bad_timing
            result = evaluate_baseline_eligibility(**kwargs)
            assert result.eligible is False, bad_timing

    def test_unresolved_data_quality_issue_is_ineligible_even_with_a_perfect_score(self) -> None:
        kwargs = _all_passing_kwargs()
        kwargs["direction_score"] = 8
        kwargs["has_unresolved_data_quality_issue"] = True
        result = evaluate_baseline_eligibility(**kwargs)
        assert result.eligible is False

    def test_missing_liquidity_data_fails_closed_not_open(self) -> None:
        kwargs = _all_passing_kwargs()
        kwargs["avg_daily_dollar_volume"] = None
        result = evaluate_baseline_eligibility(**kwargs)
        assert result.eligible is False


class TestRejectedEventWithMultipleFailures:
    def test_reports_every_failing_condition_not_just_the_first(self) -> None:
        result = evaluate_baseline_eligibility(
            direction_score=2,
            expected_move_pct=Decimal("1.0"),
            avg_daily_dollar_volume=Decimal("1_000_000"),
            num_analyst_estimates=1,
            timing_category="UNKNOWN",
            evidence_is_fresh=False,
            has_portfolio_capacity=False,
            has_sector_capacity=True,
            has_unresolved_data_quality_issue=True,
        )
        assert result.eligible is False
        failing_keys = {c.condition_key for c in result.conditions if not c.passed}
        assert failing_keys == {
            "DIRECTION_SCORE",
            "EXPECTED_MOVE",
            "LIQUIDITY",
            "ANALYST_COVERAGE",
            "VERIFIED_EVENT_TIMING",
            "FRESH_EVIDENCE",
            "PORTFOLIO_CAPACITY",
            "NO_UNRESOLVED_DATA_QUALITY_ISSUE",
        }
        assert "SECTOR_CAPACITY" not in failing_keys
