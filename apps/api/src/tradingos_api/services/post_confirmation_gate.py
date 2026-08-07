"""The Tactical post-confirmation eligibility gate (Revision Prompt 7,
HES-4/HES-6). `TRADE_ADD_CONFIRMED` may only be *proposed* — not
guaranteed — when every one of the conditions below holds; this module
answers "is a post-confirmation committee run even worth attempting,"
it never itself produces the new recommendation (that's a fresh
`run_recommendation_pipeline()` call, TACTICAL lane, with a fresh
evidence bundle — HES-4's "new recommendation with a new entry, stop,
target, time exit, and risk budget").

**HES-6, enforced here as an absolute, non-negotiable check:** no
add-on is ever proposed after an adverse (negative) gap, full stop —
"not even with a new catalyst, not even if [the general add-on rule's]
precondition would otherwise be satisfied." This is checked
independently of the three post-earnings confirmation gates
(Revision Prompt 5's `services/post_earnings_confirmation.py`), because
a negative gap blocks the proposal even in the hypothetical case where
somehow every other gate looked fine."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from tradingos_api.services.post_earnings_confirmation import PostEarningsConfirmationResult

CALCULATION_VERSION = "v1"


@dataclass(frozen=True)
class PostConfirmationEligibility:
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION


def evaluate_post_confirmation_eligibility(
    *,
    post_earnings_result: PostEarningsConfirmationResult,
    gap_pct: Decimal,
    liquidity_passed: bool,
) -> PostConfirmationEligibility:
    reasons: list[str] = []

    if gap_pct < 0:
        reasons.append(
            "HES-6: no add-on is ever proposed after an adverse (negative) gap, full "
            "stop — not even with a new catalyst"
        )
    if not post_earnings_result.results_gate_passed:
        reasons.append("earnings result direction did not pass the configured thresholds")
    if not post_earnings_result.guidance_gate_passed:
        reasons.append("guidance direction did not pass the configured thresholds")
    if not post_earnings_result.market_reaction_gate_passed:
        reasons.append(
            "market reaction gate failed (reversal, failed breakout, or sector/market misalignment)"
        )
    if not liquidity_passed:
        reasons.append("liquidity is inadequate")

    return PostConfirmationEligibility(eligible=not reasons, reasons=reasons)
