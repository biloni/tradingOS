"""Hard veto engine tests (Revision Prompt 7) — "every veto produces a
user-readable explanation code," and the specific "gap-through-stop" /
"event date correction" scenarios named in the prompt's own test list."""

from __future__ import annotations

from datetime import UTC, date, datetime

from tradingos_api.services.hard_vetoes import (
    HardVetoInputs,
    any_veto_triggered,
    evaluate_hard_vetoes,
    triggered_vetoes,
)


def _clean_inputs(**overrides: object) -> HardVetoInputs:
    defaults: dict[str, object] = {"has_stale_required_data": False}
    defaults.update(overrides)
    return HardVetoInputs(**defaults)  # type: ignore[arg-type]


class TestEveryVetoProducesAUserReadableExplanationCode:
    def test_all_ten_vetoes_pass_cleanly_when_nothing_is_wrong(self) -> None:
        results = evaluate_hard_vetoes(_clean_inputs())
        assert len(results) == 10
        assert not any_veto_triggered(results)
        for r in results:
            assert r.explanation == "OK"

    def test_each_triggered_veto_has_a_non_empty_stable_code_and_readable_sentence(self) -> None:
        inputs = _clean_inputs(
            has_stale_required_data=True,
            stale_data_detail="MarketBar is 4 days old",
            event_timing_verified=False,
            event_timing_category="UNKNOWN",
            liquidity_passed=False,
            risk_or_sector_limit_breached=True,
            risk_or_sector_limit_detail="sector exposure would exceed 25%",
            has_current_price=False,
            evidence_leakage_detected=True,
            kill_switch_active=True,
            broker_environment_ambiguous=True,
            attribution_ambiguous=True,
            recommendation_review_date=date(2020, 1, 1),
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
        )
        results = evaluate_hard_vetoes(inputs)
        fired = triggered_vetoes(results)
        assert len(fired) == 10  # every check triggers under these inputs
        for veto in fired:
            assert veto.veto_code.isupper()
            assert veto.veto_code.replace("_", "").isalnum()
            assert veto.explanation != "OK"
            assert veto.explanation.startswith("Blocked:")
            assert veto.explanation.endswith(".")


class TestEventDateCorrection:
    def test_unverified_timing_after_a_correction_still_blocks(self) -> None:
        """Mirrors Revision Prompt 4's calendar-correction path: a
        corrected event whose new timing is still not confirmed must
        continue to block, not be waved through because "something" was
        provided."""
        inputs = _clean_inputs(
            event_timing_verified=False, event_timing_category="DATE_UNCONFIRMED"
        )
        results = evaluate_hard_vetoes(inputs)
        veto = next(r for r in results if r.veto_code == "UNVERIFIED_EVENT_TIMING")
        assert veto.triggered is True
        assert "DATE_UNCONFIRMED" in veto.explanation

    def test_a_verified_corrected_timing_no_longer_blocks(self) -> None:
        inputs = _clean_inputs(event_timing_verified=True, event_timing_category="AFTER_CLOSE")
        results = evaluate_hard_vetoes(inputs)
        veto = next(r for r in results if r.veto_code == "UNVERIFIED_EVENT_TIMING")
        assert veto.triggered is False


class TestExpiredRecommendation:
    def test_review_date_in_the_past_triggers(self) -> None:
        inputs = _clean_inputs(
            recommendation_review_date=date(2026, 1, 1),
            as_of=datetime(2026, 6, 1, tzinfo=UTC),
        )
        results = evaluate_hard_vetoes(inputs)
        veto = next(r for r in results if r.veto_code == "RECOMMENDATION_EXPIRED")
        assert veto.triggered is True

    def test_review_date_in_the_future_does_not_trigger(self) -> None:
        inputs = _clean_inputs(
            recommendation_review_date=date(2027, 1, 1),
            as_of=datetime(2026, 6, 1, tzinfo=UTC),
        )
        results = evaluate_hard_vetoes(inputs)
        veto = next(r for r in results if r.veto_code == "RECOMMENDATION_EXPIRED")
        assert veto.triggered is False

    def test_missing_review_date_or_as_of_never_triggers(self) -> None:
        results = evaluate_hard_vetoes(_clean_inputs())
        veto = next(r for r in results if r.veto_code == "RECOMMENDATION_EXPIRED")
        assert veto.triggered is False


class TestMissingPriceOrExpectedMove:
    def test_missing_both_names_both_in_the_explanation(self) -> None:
        inputs = _clean_inputs(has_current_price=False, has_expected_move=False)
        results = evaluate_hard_vetoes(inputs)
        veto = next(r for r in results if r.veto_code == "MISSING_PRICE_OR_EXPECTED_MOVE")
        assert veto.triggered is True
        assert "current price" in veto.explanation
        assert "expected move" in veto.explanation
