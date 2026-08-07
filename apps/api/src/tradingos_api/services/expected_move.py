"""Expected-move calculation (Revision Prompt 5,
docs/HYBRID_EARNINGS_STRATEGY.md). Three independent estimates — ATR
percentage, historical median absolute gap, and options-implied
movement (when available) — are always stored separately
(`EventExpectedMoveSnapshot`, R3); `selected_expected_move_pct` is the
one value the baseline backtest reads, deliberately
`max(atr_pct, historical_median_gap_pct)` so it stays comparable with
the already-validated six-month baseline test. Option-implied movement
is surfaced as a live diagnostic comparison only — it never silently
substitutes into `selected_expected_move_pct` ("do not silently change
strategy logic")."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal

CALCULATION_VERSION = "v1"

_MAX_HISTORICAL_GAP_EVENTS = 3


@dataclass(frozen=True)
class ExpectedMoveResult:
    atr_based_move_pct: Decimal | None
    historical_gap_move_pct: Decimal | None
    historical_gap_event_count: int
    option_implied_move_pct: Decimal | None
    option_implied_status: str
    selected_expected_move_pct: Decimal | None
    selection_method: str
    option_implied_diagnostic_delta_pct: Decimal | None
    calculation_version: str = CALCULATION_VERSION


def compute_expected_move(
    *,
    atr_based_move_pct: Decimal | None,
    prior_gap_abs_pcts: list[Decimal],
    option_implied_move_pct: Decimal | None,
    option_implied_available: bool,
) -> ExpectedMoveResult:
    """`prior_gap_abs_pcts` should be the up-to-3 most recent eligible
    earnings events' absolute tradable gap percentages (already
    split-adjusted by the caller — this function does no adjustment
    itself)."""
    recent_gaps = prior_gap_abs_pcts[-_MAX_HISTORICAL_GAP_EVENTS:]
    historical_gap_move_pct = Decimal(str(statistics.median(recent_gaps))) if recent_gaps else None

    if atr_based_move_pct is not None and historical_gap_move_pct is not None:
        selected = max(atr_based_move_pct, historical_gap_move_pct)
        method = "max(ATR%, historical_median_gap%)"
    elif atr_based_move_pct is not None:
        selected = atr_based_move_pct
        method = "ATR% only (no eligible historical gaps)"
    elif historical_gap_move_pct is not None:
        selected = historical_gap_move_pct
        method = "historical_median_gap% only (ATR unavailable)"
    else:
        selected = None
        method = "unavailable — neither ATR% nor a historical gap could be computed"

    option_implied_status = "OK" if option_implied_available else "CAPABILITY_UNAVAILABLE"
    diagnostic_delta = None
    if option_implied_available and option_implied_move_pct is not None and selected is not None:
        diagnostic_delta = option_implied_move_pct - selected

    return ExpectedMoveResult(
        atr_based_move_pct=atr_based_move_pct,
        historical_gap_move_pct=historical_gap_move_pct,
        historical_gap_event_count=len(recent_gaps),
        option_implied_move_pct=option_implied_move_pct if option_implied_available else None,
        option_implied_status=option_implied_status,
        selected_expected_move_pct=selected,
        selection_method=method,
        option_implied_diagnostic_delta_pct=diagnostic_delta,
    )
