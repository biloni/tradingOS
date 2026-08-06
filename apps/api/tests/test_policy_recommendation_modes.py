"""Policy checks for the v2 amendment's investment/tactical mode
separation (PROJECT_INSTRUCTIONS.md -> PRODUCT MODES)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingos_api.policy.recommendation_modes import (
    ACTIONS_BY_MODE,
    InvestmentAction,
    ModeActionMismatchError,
    ModeIdentitySeparationError,
    RecommendationMode,
    SilentModeConversionError,
    TacticalAction,
    ThesisAttributes,
    assert_action_valid_for_mode,
    assert_distinct_mode_attributes,
    assert_no_silent_mode_conversion,
)


def _thesis(**overrides: object) -> ThesisAttributes:
    defaults: dict[str, object] = {
        "recommendation_id": "rec-investment-1",
        "mode": RecommendationMode.INVESTMENT,
        "risk_budget_pct": Decimal("0.0100"),
        "horizon_days_min": 90,
        "horizon_days_max": 730,
        "invalidation_condition": "closes below the 200-day SMA on a weekly basis",
        "accounting_tag": "invest-core",
    }
    defaults.update(overrides)
    return ThesisAttributes(**defaults)  # type: ignore[arg-type]


class TestExactlyTwoModes:
    def test_two_modes(self) -> None:
        assert {m.value for m in RecommendationMode} == {"INVESTMENT", "TACTICAL"}


class TestActionSetsAreModeExclusive:
    def test_investment_action_set_matches_spec(self) -> None:
        assert {a.value for a in InvestmentAction} == {
            "INVEST_BUY",
            "INVEST_ADD",
            "INVEST_HOLD",
            "INVEST_TRIM",
            "INVEST_EXIT",
            "INVEST_WATCH",
            "NO_ACTION",
        }

    def test_tactical_action_set_matches_spec(self) -> None:
        assert {a.value for a in TacticalAction} == {
            "TRADE_ENTER",
            "TRADE_WAIT",
            "TRADE_ADD_CONFIRMED",
            "TRADE_HOLD",
            "TRADE_TAKE_PARTIAL",
            "TRADE_TIGHTEN_STOP",
            "TRADE_EXIT",
            "TRADE_AVOID",
            "NO_ACTION",
        }

    def test_action_sets_only_overlap_on_no_action(self) -> None:
        investment_actions = ACTIONS_BY_MODE[RecommendationMode.INVESTMENT]
        tactical_actions = ACTIONS_BY_MODE[RecommendationMode.TACTICAL]
        assert investment_actions & tactical_actions == {"NO_ACTION"}

    def test_investment_mode_rejects_a_tactical_action(self) -> None:
        with pytest.raises(ModeActionMismatchError):
            assert_action_valid_for_mode(RecommendationMode.INVESTMENT, "TRADE_ENTER")

    def test_tactical_mode_rejects_an_investment_action(self) -> None:
        with pytest.raises(ModeActionMismatchError):
            assert_action_valid_for_mode(RecommendationMode.TACTICAL, "INVEST_BUY")

    def test_no_action_valid_in_both_modes(self) -> None:
        assert_action_valid_for_mode(RecommendationMode.INVESTMENT, "NO_ACTION")
        assert_action_valid_for_mode(RecommendationMode.TACTICAL, "NO_ACTION")

    def test_each_modes_own_action_is_valid(self) -> None:
        assert_action_valid_for_mode(RecommendationMode.INVESTMENT, "INVEST_BUY")
        assert_action_valid_for_mode(RecommendationMode.TACTICAL, "TRADE_ENTER")


class TestDistinctModeAttributes:
    def test_same_symbol_two_modes_two_ids_is_fine(self) -> None:
        investment = _thesis(recommendation_id="rec-inv-AAPL")
        tactical = _thesis(
            recommendation_id="rec-tac-AAPL",
            mode=RecommendationMode.TACTICAL,
            horizon_days_min=1,
            horizon_days_max=10,
            accounting_tag="trade-swing",
        )
        assert_distinct_mode_attributes(investment, tactical)  # should not raise

    def test_sharing_a_recommendation_id_is_rejected(self) -> None:
        investment = _thesis(recommendation_id="rec-shared")
        tactical = _thesis(
            recommendation_id="rec-shared",
            mode=RecommendationMode.TACTICAL,
        )
        with pytest.raises(ModeIdentitySeparationError):
            assert_distinct_mode_attributes(investment, tactical)

    def test_equal_risk_budgets_across_modes_is_not_itself_a_violation(self) -> None:
        # "Separate" means independently attributed, not required to
        # differ numerically — two legitimately-equal risk budgets must
        # not false-positive.
        investment = _thesis(recommendation_id="rec-inv-2", risk_budget_pct=Decimal("0.0100"))
        tactical = _thesis(
            recommendation_id="rec-tac-2",
            mode=RecommendationMode.TACTICAL,
            risk_budget_pct=Decimal("0.0100"),
        )
        assert_distinct_mode_attributes(investment, tactical)

    def test_wrong_mode_tag_on_investment_argument_raises(self) -> None:
        not_investment = _thesis(mode=RecommendationMode.TACTICAL)
        tactical = _thesis(recommendation_id="rec-tac-3", mode=RecommendationMode.TACTICAL)
        with pytest.raises(ValueError, match="INVESTMENT"):
            assert_distinct_mode_attributes(not_investment, tactical)

    def test_wrong_mode_tag_on_tactical_argument_raises(self) -> None:
        investment = _thesis(recommendation_id="rec-inv-4")
        not_tactical = _thesis(recommendation_id="rec-tac-4", mode=RecommendationMode.INVESTMENT)
        with pytest.raises(ValueError, match="TACTICAL"):
            assert_distinct_mode_attributes(investment, not_tactical)


class TestNoSilentModeConversion:
    def test_same_mode_never_raises(self) -> None:
        assert_no_silent_mode_conversion(
            RecommendationMode.INVESTMENT,
            RecommendationMode.INVESTMENT,
            explicit_user_action=False,
        )

    def test_mode_change_without_explicit_action_is_rejected(self) -> None:
        with pytest.raises(SilentModeConversionError):
            assert_no_silent_mode_conversion(
                RecommendationMode.INVESTMENT,
                RecommendationMode.TACTICAL,
                explicit_user_action=False,
            )

    def test_mode_change_with_explicit_action_is_allowed(self) -> None:
        assert_no_silent_mode_conversion(
            RecommendationMode.TACTICAL,
            RecommendationMode.INVESTMENT,
            explicit_user_action=True,
        )
