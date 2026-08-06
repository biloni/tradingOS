"""Split-adjusted overnight-gap computation (Revision Prompt 4) —
feeds `EarningsHistoricalGap.gap_pct` (R3). Must be called with
split-adjusted closes/opens (`MarketBar.adjusted=True`,
`AlpacaStockDataProvider` always requests `Adjustment.SPLIT`, see
`providers/alpaca_evidence.py`) — the "missing split adjustment"
data-quality gate (`services/data_quality.py`) is exactly what catches a
caller passing unadjusted bars into this function by mistake, which
would otherwise report a large false "gap" across a split's ex-date
that is actually just the split's price-ratio jump, not a real overnight
move.
"""

from __future__ import annotations

from decimal import Decimal


def compute_overnight_gap_pct(prior_close: Decimal, current_open: Decimal) -> Decimal:
    """`(current_open - prior_close) / prior_close`, as a percentage.
    Callers must pass split-adjusted prices — this function has no way
    to detect an unadjusted input itself, that is what the
    `check_missing_split_adjustment` data-quality gate is for."""
    if prior_close == 0:
        raise ValueError("prior_close cannot be zero")
    return ((current_open - prior_close) / prior_close) * Decimal("100")
