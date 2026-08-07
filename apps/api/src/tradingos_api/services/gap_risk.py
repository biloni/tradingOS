"""Overnight gap-through-stop modeling (Revision Prompt 7, HES-5):
"The system must model overnight gap risk explicitly wherever a stop is
shown... a numeric gap-risk estimate accompanies the stop, not just the
stop price alone" and "A stop order is never represented as a guarantee
of the stop price."

`estimate_stop_fill_under_gap()` computes what a stop would actually
fill at if the overnight gap carries price through the stop before the
market can trade at the stop price itself — a sell-stop's fill in that
case is the (worse) gapped-open price, not the stop price. `disclosure`
is always populated, even when the gap doesn't carry through the stop —
the "not a guarantee" text is a standing property of every stop order
on an earnings-adjacent position, not a warning that only appears when
something already went wrong."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

CALCULATION_VERSION = "v1"

StopSide = Literal["SELL_STOP", "BUY_STOP"]


@dataclass(frozen=True)
class GapThroughStopEstimate:
    stop_price: Decimal
    prior_close: Decimal
    gap_pct: Decimal
    implied_open: Decimal
    estimated_fill_price: Decimal
    gapped_through_stop: bool
    slippage_vs_stop: Decimal
    disclosure: str
    calculation_version: str = CALCULATION_VERSION


def estimate_stop_fill_under_gap(
    *,
    stop_price: Decimal,
    prior_close: Decimal,
    gap_pct: Decimal,
    side: StopSide = "SELL_STOP",
) -> GapThroughStopEstimate:
    if prior_close <= 0:
        raise ValueError("prior_close must be positive")
    if stop_price <= 0:
        raise ValueError("stop_price must be positive")

    implied_open = prior_close * (Decimal(1) + gap_pct / Decimal(100))

    if side == "SELL_STOP":
        gapped_through = implied_open < stop_price
        estimated_fill_price = implied_open if gapped_through else stop_price
        slippage_vs_stop = stop_price - estimated_fill_price
    else:
        gapped_through = implied_open > stop_price
        estimated_fill_price = implied_open if gapped_through else stop_price
        slippage_vs_stop = estimated_fill_price - stop_price

    if gapped_through:
        disclosure = (
            f"This stop is NOT a guaranteed execution price. Under this gap scenario "
            f"({gap_pct}%), the implied open ({implied_open}) is on the adverse side of "
            f"the {stop_price} stop trigger — the estimated actual fill is "
            f"{estimated_fill_price}, {abs(slippage_vs_stop)} worse than the stop price "
            "shown. A real overnight gap can be materially larger or smaller than this "
            "estimate."
        )
    else:
        disclosure = (
            f"This stop is NOT a guaranteed execution price. Under this gap scenario "
            f"({gap_pct}%), the implied open ({implied_open}) does not carry through the "
            f"{stop_price} stop, but a real overnight gap can still be materially larger "
            "than this estimate and fill far worse than shown."
        )

    return GapThroughStopEstimate(
        stop_price=stop_price,
        prior_close=prior_close,
        gap_pct=gap_pct,
        implied_open=implied_open,
        estimated_fill_price=estimated_fill_price,
        gapped_through_stop=gapped_through,
        slippage_vs_stop=slippage_vs_stop,
        disclosure=disclosure,
    )
