"""Tactical earnings-trade position sizing (Revision Prompt 7, HES-3).
`compute_tactical_position_size()` is the one deterministic function
that turns a risk budget and an expected move into a share quantity —
"notional equals risk budget divided by selected expected-move
percentage, then is reduced by allocation, sector, correlation,
liquidity, speculative-name, and cash constraints" (the prompt's own
wording, implemented as six sequential caps applied in that order, each
recorded whether or not it actually bound, so a reviewer can see exactly
which constraint (if any) reduced the raw risk-based size).

Pure, DB-agnostic — the caller (`services/recommendation_pipeline.py`)
gathers every input from wherever it actually lives (`RiskPolicy`,
current portfolio positions, Revision Prompt 4's liquidity evidence),
the same boundary Revision Prompt 5's `baseline_eligibility.py`
established."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

CALCULATION_VERSION = "v1"

# Versioned defaults (principle 8) — HES-3's own stated numbers.
DEFAULT_EARNINGS_RISK_BUDGET_PCT = Decimal("0.25")
MAX_EARNINGS_RISK_BUDGET_PCT = Decimal("0.50")
DEFAULT_MAX_POSITION_ALLOCATION_PCT = Decimal("15.00")
DEFAULT_MAX_SECTOR_ALLOCATION_PCT = Decimal("25.00")
DEFAULT_MAX_CONCURRENT_EARNINGS_TRADES = 3
DEFAULT_SLIPPAGE_BPS = Decimal("5")


@dataclass(frozen=True)
class SizingConstraint:
    constraint_key: str
    limit_notional: Decimal
    notional_before: Decimal
    notional_after: Decimal
    binding: bool


@dataclass(frozen=True)
class PositionSizingResult:
    risk_budget_pct: Decimal
    expected_move_pct: Decimal
    raw_risk_based_notional: Decimal
    constraints: list[SizingConstraint] = field(default_factory=list)
    final_notional: Decimal = Decimal(0)
    final_quantity: int = 0
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS
    binding_constraint_keys: list[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION


def _apply_cap(
    constraint_key: str, notional_before: Decimal, limit_notional: Decimal
) -> SizingConstraint:
    notional_after = min(notional_before, max(limit_notional, Decimal(0)))
    return SizingConstraint(
        constraint_key=constraint_key,
        limit_notional=limit_notional,
        notional_before=notional_before,
        notional_after=notional_after,
        binding=notional_after < notional_before,
    )


def compute_tactical_position_size(
    *,
    account_equity: Decimal,
    risk_budget_pct: Decimal,
    expected_move_pct: Decimal,
    price: Decimal,
    max_position_pct: Decimal,
    max_sector_pct: Decimal,
    sector_current_notional: Decimal,
    max_correlated_group_pct: Decimal,
    correlated_group_current_notional: Decimal,
    avg_daily_dollar_volume: Decimal,
    max_liquidity_pct_of_adv: Decimal,
    is_speculative_name: bool,
    speculative_position_pct_cap: Decimal,
    available_cash: Decimal,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> PositionSizingResult:
    """`expected_move_pct` must already be the lane's `selected_expected_move_pct`
    (Revision Prompt 5's `expected_move.py`) — this function does not
    choose between ATR/historical-gap/option-implied itself. Raises
    `ValueError` if `expected_move_pct` is not positive — a zero or
    negative expected move makes the risk-budget-divided-by-move formula
    meaningless, and the caller should have already vetoed on
    `MISSING_PRICE_OR_EXPECTED_MOVE` before ever reaching this function."""
    if expected_move_pct <= 0:
        raise ValueError("expected_move_pct must be positive")
    if price <= 0:
        raise ValueError("price must be positive")

    risk_dollars = account_equity * (risk_budget_pct / Decimal(100))
    raw_notional = risk_dollars / (expected_move_pct / Decimal(100))

    constraints: list[SizingConstraint] = []
    running = raw_notional

    allocation_cap = account_equity * (max_position_pct / Decimal(100))
    constraints.append(_apply_cap("MAX_POSITION_ALLOCATION", running, allocation_cap))
    running = constraints[-1].notional_after

    sector_remaining = account_equity * (max_sector_pct / Decimal(100)) - sector_current_notional
    constraints.append(_apply_cap("MAX_SECTOR_EXPOSURE", running, sector_remaining))
    running = constraints[-1].notional_after

    correlation_cap = account_equity * (max_correlated_group_pct / Decimal(100))
    correlation_remaining = correlation_cap - correlated_group_current_notional
    constraints.append(_apply_cap("MAX_CORRELATED_GROUP_EXPOSURE", running, correlation_remaining))
    running = constraints[-1].notional_after

    liquidity_cap = avg_daily_dollar_volume * (max_liquidity_pct_of_adv / Decimal(100))
    constraints.append(_apply_cap("LIQUIDITY_CAP", running, liquidity_cap))
    running = constraints[-1].notional_after

    if is_speculative_name:
        speculative_cap = account_equity * (speculative_position_pct_cap / Decimal(100))
        constraints.append(_apply_cap("SPECULATIVE_NAME_CAP", running, speculative_cap))
        running = constraints[-1].notional_after

    constraints.append(_apply_cap("AVAILABLE_CASH", running, available_cash))
    running = constraints[-1].notional_after

    final_notional = max(running, Decimal(0))
    final_quantity = int((final_notional / price).to_integral_value(rounding=ROUND_DOWN))
    final_notional = Decimal(final_quantity) * price  # re-derive from whole shares actually bought

    return PositionSizingResult(
        risk_budget_pct=risk_budget_pct,
        expected_move_pct=expected_move_pct,
        raw_risk_based_notional=raw_notional,
        constraints=constraints,
        final_notional=final_notional,
        final_quantity=final_quantity,
        slippage_bps=slippage_bps,
        binding_constraint_keys=[c.constraint_key for c in constraints if c.binding],
    )
