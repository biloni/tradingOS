"""Investment/tactical mode separation (PROJECT_INSTRUCTIONS.md, "TradingOS
v2 Decision and Execution Amendment" -> PRODUCT MODES).

A symbol may carry both an investment thesis (~3-24 months) and a tactical
setup (~1-10 trading days) at the same time, but the amendment requires
them to never share identity, risk budget, horizon, invalidation
condition, or accounting attribution, and forbids a price move alone from
converting one into the other. This module is the deterministic check for
both rules; it does not touch `models.recommendations.Recommendation`
(no new column, no migration) — a future phase wires a real `mode` field
through the schema once the rest of the v2 feature set is scoped.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RecommendationMode(StrEnum):
    INVESTMENT = "INVESTMENT"
    TACTICAL = "TACTICAL"


class InvestmentAction(StrEnum):
    INVEST_BUY = "INVEST_BUY"
    INVEST_ADD = "INVEST_ADD"
    INVEST_HOLD = "INVEST_HOLD"
    INVEST_TRIM = "INVEST_TRIM"
    INVEST_EXIT = "INVEST_EXIT"
    INVEST_WATCH = "INVEST_WATCH"
    NO_ACTION = "NO_ACTION"


class TacticalAction(StrEnum):
    TRADE_ENTER = "TRADE_ENTER"
    TRADE_WAIT = "TRADE_WAIT"
    TRADE_ADD_CONFIRMED = "TRADE_ADD_CONFIRMED"
    TRADE_HOLD = "TRADE_HOLD"
    TRADE_TAKE_PARTIAL = "TRADE_TAKE_PARTIAL"
    TRADE_TIGHTEN_STOP = "TRADE_TIGHTEN_STOP"
    TRADE_EXIT = "TRADE_EXIT"
    TRADE_AVOID = "TRADE_AVOID"
    NO_ACTION = "NO_ACTION"


# NO_ACTION is the one action legitimately shared by both action sets
# (both modes must be able to recommend doing nothing) — everything else
# is mode-exclusive by construction, verified in
# test_policy_recommendation_modes.py::test_action_sets_only_overlap_on_no_action.
ACTIONS_BY_MODE: dict[RecommendationMode, frozenset[str]] = {
    RecommendationMode.INVESTMENT: frozenset(a.value for a in InvestmentAction),
    RecommendationMode.TACTICAL: frozenset(a.value for a in TacticalAction),
}


class ModeActionMismatchError(ValueError):
    """Raised when an action from one mode's vocabulary is used under the
    other mode — e.g. TRADE_ENTER proposed for an INVESTMENT recommendation."""


class ModeIdentitySeparationError(ValueError):
    """Raised when an investment thesis and a tactical setup for the same
    symbol share a recommendation_id — they must always be two distinct
    records, never one row wearing two hats."""


class SilentModeConversionError(ValueError):
    """Raised when a mode changes without an explicit, human-driven
    action — a short-term price move must never by itself flip an
    investment into a trade or a trade into an investment."""


def assert_action_valid_for_mode(mode: RecommendationMode, action: str) -> None:
    if action not in ACTIONS_BY_MODE[mode]:
        raise ModeActionMismatchError(
            f"{action!r} is not a valid {mode.value} action "
            f"(valid: {sorted(ACTIONS_BY_MODE[mode])})"
        )


@dataclass(frozen=True)
class ThesisAttributes:
    """One mode's governing attributes for one symbol. A symbol with both
    an investment thesis and a tactical setup has two independent
    instances of this — one per mode — each with its own risk budget,
    horizon, invalidation condition, and accounting tag; nothing here is
    ever shared by reference between the two."""

    recommendation_id: str
    mode: RecommendationMode
    risk_budget_pct: Decimal
    horizon_days_min: int
    horizon_days_max: int
    invalidation_condition: str
    accounting_tag: str


def assert_distinct_mode_attributes(
    investment: ThesisAttributes, tactical: ThesisAttributes
) -> None:
    """The one hard identity requirement the amendment states explicitly:
    separate recommendation_ids. The other four attributes (risk budget,
    horizon, invalidation condition, accounting tag) are "separate" in
    the sense the amendment means it — independently attributed per mode,
    which `ThesisAttributes` being two distinct instances already
    guarantees structurally — not required to differ numerically (e.g.
    both legitimately defaulting to the same risk-budget percentage is
    not a violation)."""
    if investment.mode is not RecommendationMode.INVESTMENT:
        raise ValueError("`investment` argument must carry RecommendationMode.INVESTMENT")
    if tactical.mode is not RecommendationMode.TACTICAL:
        raise ValueError("`tactical` argument must carry RecommendationMode.TACTICAL")
    if investment.recommendation_id == tactical.recommendation_id:
        raise ModeIdentitySeparationError(
            "an investment thesis and a tactical setup for the same symbol "
            "must carry distinct recommendation_ids"
        )


def assert_no_silent_mode_conversion(
    previous_mode: RecommendationMode,
    new_mode: RecommendationMode,
    *,
    explicit_user_action: bool,
) -> None:
    if previous_mode != new_mode and not explicit_user_action:
        raise SilentModeConversionError(
            f"cannot change mode {previous_mode.value} -> {new_mode.value} "
            "without an explicit user action"
        )
