"""Post-earnings confirmation features (Revision Prompt 5,
docs/HYBRID_EARNINGS_STRATEGY.md HES-4). Feeds
`models.market_evidence.PostEarningsConfirmationSnapshot`'s three
gates plus the richer diagnostic detail behind them. Every component
that needs intraday data explicitly reports `CAPABILITY_UNAVAILABLE`
(not `FAIL`, not `MISSING_DATA`) when the caller signals the current
data entitlement doesn't supply it — a structural limit is never
disguised as a transient gap or a failing condition."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingos_api.services.scoring_common import ComponentResult


@dataclass(frozen=True)
class PostEarningsConfirmationResult:
    components: list[ComponentResult]
    results_gate_passed: bool
    guidance_gate_passed: bool
    market_reaction_gate_passed: bool
    all_gates_passed: bool


def _eps_surprise(actual_eps: Decimal | None, estimate_eps: Decimal | None) -> ComponentResult:
    """`(actual - estimate) / abs(estimate) * 100` — dividing by the
    absolute value of the estimate (not the signed estimate) is the
    "correct ... denominator handling" this component is required to
    get right: with a signed denominator, a company estimated to lose
    money (`estimate < 0`) that beats by losing *less* than expected
    would otherwise compute a surprise with the wrong sign."""
    if actual_eps is None or estimate_eps is None:
        return ComponentResult(
            "EPS_SURPRISE", 1, None, "MISSING_DATA", "missing actual or estimate EPS"
        )
    if estimate_eps == 0:
        return ComponentResult(
            "EPS_SURPRISE",
            1,
            actual_eps,
            "MISSING_DATA",
            "estimate EPS is zero — surprise percentage is undefined, raw actual reported instead",
        )
    surprise = ((actual_eps - estimate_eps) / abs(estimate_eps)) * Decimal(100)
    status = "PASS" if surprise > 0 else "FAIL"
    return ComponentResult("EPS_SURPRISE", 1, surprise, status, None)


def _revenue_surprise(
    actual_revenue: Decimal | None, estimate_revenue: Decimal | None
) -> ComponentResult:
    if actual_revenue is None or estimate_revenue is None:
        return ComponentResult(
            "REVENUE_SURPRISE", 2, None, "MISSING_DATA", "missing actual or estimate revenue"
        )
    if estimate_revenue == 0:
        return ComponentResult(
            "REVENUE_SURPRISE",
            2,
            actual_revenue,
            "MISSING_DATA",
            "estimate revenue is zero — surprise percentage is undefined",
        )
    surprise = ((actual_revenue - estimate_revenue) / abs(estimate_revenue)) * Decimal(100)
    status = "PASS" if surprise > 0 else "FAIL"
    return ComponentResult("REVENUE_SURPRISE", 2, surprise, status, None)


def _guidance_direction(
    new_guidance_midpoint: Decimal | None,
    prior_guidance_midpoint: Decimal | None,
    consensus_midpoint: Decimal | None,
) -> ComponentResult:
    """A no-guidance quarter is its own explicit outcome
    (`NONE_PROVIDED`), never defaulted to "in line" (HES-4)."""
    if new_guidance_midpoint is None:
        return ComponentResult("GUIDANCE_DIRECTION", 3, None, "MISSING_DATA", "NONE_PROVIDED")
    reference = (
        prior_guidance_midpoint if prior_guidance_midpoint is not None else consensus_midpoint
    )
    if reference is None:
        return ComponentResult(
            "GUIDANCE_DIRECTION",
            3,
            new_guidance_midpoint,
            "MISSING_DATA",
            "no prior guidance or consensus to compare against",
        )
    delta = new_guidance_midpoint - reference
    if delta > 0:
        status, direction = "PASS", "RAISED"
    elif delta < 0:
        status, direction = "FAIL", "LOWERED"
    else:
        status, direction = "FAIL", "IN_LINE"
    return ComponentResult("GUIDANCE_DIRECTION", 3, delta, status, direction)


def _initial_gap_direction(gap_pct: Decimal | None) -> ComponentResult:
    if gap_pct is None:
        return ComponentResult("INITIAL_GAP_DIRECTION", 4, None, "MISSING_DATA", "no gap computed")
    status = "PASS" if gap_pct > 0 else "FAIL"
    return ComponentResult("INITIAL_GAP_DIRECTION", 4, gap_pct, status, None)


def _first_n_minute_range(
    range_pct: Decimal | None, *, minutes: int, has_intraday_capability: bool
) -> ComponentResult:
    key = f"FIRST_{minutes}MIN_RANGE"
    order = 5 if minutes == 30 else 6
    if not has_intraday_capability:
        return ComponentResult(
            key, order, None, "CAPABILITY_UNAVAILABLE", "no intraday feed entitled"
        )
    if range_pct is None:
        return ComponentResult(
            key, order, None, "MISSING_DATA", "intraday range not available today"
        )
    return ComponentResult(key, order, range_pct, "PASS", None)


def _vwap_hold(
    price_vs_vwap_pct: Decimal | None, *, has_intraday_capability: bool
) -> ComponentResult:
    if not has_intraday_capability:
        return ComponentResult(
            "VWAP_HOLD", 7, None, "CAPABILITY_UNAVAILABLE", "no intraday feed entitled"
        )
    if price_vs_vwap_pct is None:
        return ComponentResult("VWAP_HOLD", 7, None, "MISSING_DATA", "VWAP not available today")
    status = "PASS" if price_vs_vwap_pct > 0 else "FAIL"
    return ComponentResult("VWAP_HOLD", 7, price_vs_vwap_pct, status, None)


def _volume_ratio(day_volume: int | None, baseline_avg_volume: int | None) -> ComponentResult:
    if day_volume is None or baseline_avg_volume is None or baseline_avg_volume == 0:
        return ComponentResult(
            "VOLUME_RATIO", 8, None, "MISSING_DATA", "missing day or baseline volume"
        )
    ratio = Decimal(day_volume) / Decimal(baseline_avg_volume)
    status = "PASS" if ratio > 1 else "FAIL"
    return ComponentResult("VOLUME_RATIO", 8, ratio, status, None)


def _sector_market_alignment(
    instrument_return_pct: Decimal | None,
    sector_return_pct: Decimal | None,
    market_return_pct: Decimal | None,
) -> ComponentResult:
    if instrument_return_pct is None or sector_return_pct is None or market_return_pct is None:
        return ComponentResult(
            "SECTOR_MARKET_ALIGNMENT", 9, None, "MISSING_DATA", "missing one of the three returns"
        )
    instrument_sign = instrument_return_pct > 0
    aligned = instrument_sign == (sector_return_pct > 0) and instrument_sign == (
        market_return_pct > 0
    )
    status = "PASS" if aligned else "FAIL"
    return ComponentResult("SECTOR_MARKET_ALIGNMENT", 9, None, status, None)


def _reversal_or_failed_breakout(
    gap_pct: Decimal | None, session_open: Decimal | None, session_close: Decimal | None
) -> ComponentResult:
    """A gap in one direction that closes the session in the opposite
    direction from open — computable from daily open/close alone, no
    intraday entitlement required."""
    if gap_pct is None or session_open is None or session_close is None:
        return ComponentResult(
            "REVERSAL_FAILED_BREAKOUT",
            10,
            None,
            "MISSING_DATA",
            "missing gap or session open/close",
        )
    intraday_move = session_close - session_open
    reversed_move = (gap_pct > 0 and intraday_move < 0) or (gap_pct < 0 and intraday_move > 0)
    # PASS means "confirmed, no reversal" — a reversal is the failing case.
    status = "FAIL" if reversed_move else "PASS"
    detail = "gap reversed intraday" if reversed_move else None
    return ComponentResult("REVERSAL_FAILED_BREAKOUT", 10, intraday_move, status, detail)


def compute_post_earnings_confirmation(
    *,
    actual_eps: Decimal | None,
    estimate_eps: Decimal | None,
    actual_revenue: Decimal | None,
    estimate_revenue: Decimal | None,
    new_guidance_midpoint: Decimal | None,
    prior_guidance_midpoint: Decimal | None,
    consensus_midpoint: Decimal | None,
    gap_pct: Decimal | None,
    session_open: Decimal | None,
    session_close: Decimal | None,
    has_intraday_capability: bool,
    range_30min_pct: Decimal | None,
    range_60min_pct: Decimal | None,
    price_vs_vwap_pct: Decimal | None,
    day_volume: int | None,
    baseline_avg_volume: int | None,
    instrument_return_pct: Decimal | None,
    sector_return_pct: Decimal | None,
    market_return_pct: Decimal | None,
) -> PostEarningsConfirmationResult:
    eps = _eps_surprise(actual_eps, estimate_eps)
    revenue = _revenue_surprise(actual_revenue, estimate_revenue)
    guidance = _guidance_direction(
        new_guidance_midpoint, prior_guidance_midpoint, consensus_midpoint
    )
    gap = _initial_gap_direction(gap_pct)
    range_30 = _first_n_minute_range(
        range_30min_pct, minutes=30, has_intraday_capability=has_intraday_capability
    )
    range_60 = _first_n_minute_range(
        range_60min_pct, minutes=60, has_intraday_capability=has_intraday_capability
    )
    vwap = _vwap_hold(price_vs_vwap_pct, has_intraday_capability=has_intraday_capability)
    volume_ratio = _volume_ratio(day_volume, baseline_avg_volume)
    alignment = _sector_market_alignment(
        instrument_return_pct, sector_return_pct, market_return_pct
    )
    reversal = _reversal_or_failed_breakout(gap_pct, session_open, session_close)

    components = [
        eps,
        revenue,
        guidance,
        gap,
        range_30,
        range_60,
        vwap,
        volume_ratio,
        alignment,
        reversal,
    ]

    # The three formal PostEarningsConfirmationSnapshot gates (HES-4) —
    # each its own explicit boolean, never blended into one judgment.
    results_gate_passed = eps.status == "PASS" and revenue.status == "PASS"
    guidance_gate_passed = guidance.status == "PASS"
    market_reaction_gate_passed = (
        gap.status == "PASS" and alignment.status == "PASS" and reversal.status == "PASS"
    )
    all_gates_passed = results_gate_passed and guidance_gate_passed and market_reaction_gate_passed

    return PostEarningsConfirmationResult(
        components=components,
        results_gate_passed=results_gate_passed,
        guidance_gate_passed=guidance_gate_passed,
        market_reaction_gate_passed=market_reaction_gate_passed,
        all_gates_passed=all_gates_passed,
    )
