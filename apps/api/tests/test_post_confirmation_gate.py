"""Post-confirmation eligibility gate tests (Revision Prompt 7,
HES-4/HES-6) — the required "no averaging down after an adverse gap"
guarantee, checked independently of (and taking priority over) the
three post-earnings confirmation gates themselves."""

from __future__ import annotations

from decimal import Decimal

from tradingos_api.services.post_confirmation_gate import evaluate_post_confirmation_eligibility
from tradingos_api.services.post_earnings_confirmation import PostEarningsConfirmationResult


def _all_gates_passed_result() -> PostEarningsConfirmationResult:
    return PostEarningsConfirmationResult(
        components=[],
        results_gate_passed=True,
        guidance_gate_passed=True,
        market_reaction_gate_passed=True,
        all_gates_passed=True,
    )


class TestNoAveragingDownAfterAnAdverseGap:
    def test_negative_gap_blocks_even_when_every_other_gate_passes(self) -> None:
        """HES-6's literal requirement: "not even with a new catalyst,
        not even if [the general rule's] precondition would otherwise
        be satisfied." All three post-earnings gates pass here, and the
        proposal is still blocked purely on the gap's sign."""
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=_all_gates_passed_result(),
            gap_pct=Decimal("-2.5"),
            liquidity_passed=True,
        )
        assert eligibility.eligible is False
        assert any("HES-6" in reason for reason in eligibility.reasons)

    def test_zero_gap_is_not_treated_as_adverse(self) -> None:
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=_all_gates_passed_result(),
            gap_pct=Decimal("0"),
            liquidity_passed=True,
        )
        assert eligibility.eligible is True

    def test_positive_gap_with_all_gates_passing_is_eligible(self) -> None:
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=_all_gates_passed_result(),
            gap_pct=Decimal("4.5"),
            liquidity_passed=True,
        )
        assert eligibility.eligible is True
        assert eligibility.reasons == []


class TestThreeGateAndGate:
    def test_failed_results_gate_blocks_regardless_of_gap(self) -> None:
        result = PostEarningsConfirmationResult(
            components=[],
            results_gate_passed=False,
            guidance_gate_passed=True,
            market_reaction_gate_passed=True,
            all_gates_passed=False,
        )
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=result, gap_pct=Decimal("5.0"), liquidity_passed=True
        )
        assert eligibility.eligible is False
        assert any("earnings result direction" in reason for reason in eligibility.reasons)

    def test_failed_guidance_gate_blocks(self) -> None:
        result = PostEarningsConfirmationResult(
            components=[],
            results_gate_passed=True,
            guidance_gate_passed=False,
            market_reaction_gate_passed=True,
            all_gates_passed=False,
        )
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=result, gap_pct=Decimal("5.0"), liquidity_passed=True
        )
        assert eligibility.eligible is False

    def test_failed_market_reaction_gate_blocks(self) -> None:
        result = PostEarningsConfirmationResult(
            components=[],
            results_gate_passed=True,
            guidance_gate_passed=True,
            market_reaction_gate_passed=False,
            all_gates_passed=False,
        )
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=result, gap_pct=Decimal("5.0"), liquidity_passed=True
        )
        assert eligibility.eligible is False

    def test_inadequate_liquidity_blocks_even_with_all_three_gates_passing(self) -> None:
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=_all_gates_passed_result(),
            gap_pct=Decimal("5.0"),
            liquidity_passed=False,
        )
        assert eligibility.eligible is False
        assert any("liquidity" in reason for reason in eligibility.reasons)

    def test_multiple_failures_are_all_reported_not_just_the_first(self) -> None:
        result = PostEarningsConfirmationResult(
            components=[],
            results_gate_passed=False,
            guidance_gate_passed=False,
            market_reaction_gate_passed=False,
            all_gates_passed=False,
        )
        eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=result, gap_pct=Decimal("-1.0"), liquidity_passed=False
        )
        assert eligibility.eligible is False
        assert len(eligibility.reasons) == 5  # gap + 3 gates + liquidity
