"""Expected-move calculation tests (Revision Prompt 5) — the required
"missing-options" case, the `max(ATR%, historical_median_gap%)` baseline
selection rule, and the "do not silently change strategy logic" rule for
option-implied movement (it's a diagnostic comparison only, never fed
into `selected_expected_move_pct`)."""

from __future__ import annotations

from decimal import Decimal

from tradingos_api.services.expected_move import compute_expected_move


class TestMissingOptionsCapability:
    def test_option_implied_unavailable_reports_capability_unavailable_and_no_value(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=Decimal("3.5"),
            prior_gap_abs_pcts=[Decimal("4.0"), Decimal("5.0")],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        assert result.option_implied_status == "CAPABILITY_UNAVAILABLE"
        assert result.option_implied_move_pct is None
        assert result.option_implied_diagnostic_delta_pct is None
        # The selected baseline move must not depend on options at all.
        assert result.selected_expected_move_pct == Decimal("4.5")  # max(3.5, median(4.0, 5.0))

    def test_option_implied_value_supplied_but_marked_unavailable_is_still_dropped(self) -> None:
        """A caller passing a stray value alongside `available=False` must
        not leak it into the response — the availability flag, not a
        None-check on the value, is the source of truth."""
        result = compute_expected_move(
            atr_based_move_pct=Decimal("3.0"),
            prior_gap_abs_pcts=[],
            option_implied_move_pct=Decimal("9.9"),
            option_implied_available=False,
        )
        assert result.option_implied_move_pct is None
        assert result.option_implied_status == "CAPABILITY_UNAVAILABLE"


class TestBaselineSelectionIsMaxOfAtrAndHistoricalGap:
    def test_atr_wins_when_larger(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=Decimal("6.0"),
            prior_gap_abs_pcts=[Decimal("2.0"), Decimal("3.0")],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        assert result.selected_expected_move_pct == Decimal("6.0")
        assert "max(" in result.selection_method

    def test_historical_gap_wins_when_larger(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=Decimal("2.0"),
            prior_gap_abs_pcts=[Decimal("6.0"), Decimal("7.0"), Decimal("8.0")],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        assert result.selected_expected_move_pct == Decimal("7.0")  # median(6.0, 7.0, 8.0)

    def test_only_the_most_recent_three_gap_events_are_used(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=Decimal("1.0"),
            prior_gap_abs_pcts=[Decimal("100.0"), Decimal("2.0"), Decimal("3.0"), Decimal("4.0")],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        assert result.historical_gap_event_count == 3
        # The oldest (100.0) is dropped; median of the most recent 3 (2,3,4) is 3.
        assert result.historical_gap_move_pct == Decimal("3.0")

    def test_neither_source_available_reports_none_with_explanatory_method(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=None,
            prior_gap_abs_pcts=[],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        assert result.selected_expected_move_pct is None
        assert "unavailable" in result.selection_method


class TestOptionImpliedIsDiagnosticOnlyNeverFedBackIntoSelection:
    def test_option_implied_delta_is_computed_but_does_not_change_selected_move(self) -> None:
        result = compute_expected_move(
            atr_based_move_pct=Decimal("3.0"),
            prior_gap_abs_pcts=[Decimal("2.0")],
            option_implied_move_pct=Decimal("9.0"),
            option_implied_available=True,
        )
        assert result.selected_expected_move_pct == Decimal("3.0")  # unaffected by the 9.0
        assert result.option_implied_move_pct == Decimal("9.0")
        assert result.option_implied_diagnostic_delta_pct == Decimal("6.0")  # 9.0 - 3.0
