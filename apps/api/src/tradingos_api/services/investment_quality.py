"""The Investment lane's transparent, configurable investment-quality
feature engine (Revision Prompt 5). Deliberately never collapses into
one opaque score — `InvestmentQualityResult.components` carries 9
independent component scores, and `hard_disqualified` is a separate,
explicit veto flag, never blended into a weighted average (the same
"AND gate, not a score" philosophy `services/baseline_eligibility.py`
and HES-2 already establish for the tactical lane).

This module computes the feature snapshot only — it does not draft a
thesis, valuation narrative, or investment recommendation. A downstream
(not-yet-built, "do not create recommendations yet") workflow is
responsible for turning a passing snapshot into an `INVEST_BUY`/
`INVEST_ADD` proposal, which itself additionally requires a documented
thesis, valuation logic, horizon, review date, and thesis-invalidation
condition (DQ-1) — none of which this deterministic engine invents on
its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tradingos_api.services.analytics import relative_strength
from tradingos_api.services.scoring_common import ComponentResult

CALCULATION_VERSION = "v1"

# A documented, versioned starter classification (principle 8) — not a
# claim of completeness. Sectors here get a durability tailwind in
# component 6; every other sector is evaluated on its own merits with no
# bonus or penalty, not silently assumed non-durable.
_DURABLE_SECTORS = frozenset({"Consumer Staples", "Utilities", "Healthcare"})

# Valuation component's documented threshold (principle 8).
_PEG_REASONABLE_MAX = Decimal("2.0")

# Balance-sheet component's documented threshold.
_MAX_REASONABLE_DEBT_TO_EQUITY = Decimal("2.0")

_LONG_TERM_RS_WINDOW_DAYS = 252


@dataclass(frozen=True)
class InvestmentQualityResult:
    components: list[ComponentResult]
    hard_disqualified: bool
    disqualification_reason: str | None
    calculation_version: str = CALCULATION_VERSION


def _component_1_revenue_and_earnings_growth(
    revenue_growth_yoy_pct: Decimal | None, earnings_growth_yoy_pct: Decimal | None
) -> ComponentResult:
    if revenue_growth_yoy_pct is None or earnings_growth_yoy_pct is None:
        return ComponentResult(
            "REVENUE_EARNINGS_GROWTH", 1, None, "MISSING_DATA", "missing revenue or earnings growth"
        )
    value = revenue_growth_yoy_pct + earnings_growth_yoy_pct
    status = "PASS" if revenue_growth_yoy_pct > 0 and earnings_growth_yoy_pct > 0 else "FAIL"
    return ComponentResult("REVENUE_EARNINGS_GROWTH", 1, value, status, None)


def _component_2_margin_trend(margin_trend_bps_yoy: Decimal | None) -> ComponentResult:
    if margin_trend_bps_yoy is None:
        return ComponentResult("MARGIN_TREND", 2, None, "MISSING_DATA", "no margin trend supplied")
    status = "PASS" if margin_trend_bps_yoy > 0 else "FAIL"
    return ComponentResult("MARGIN_TREND", 2, margin_trend_bps_yoy, status, None)


def _component_3_balance_sheet_quality(
    debt_to_equity: Decimal | None, free_cash_flow_positive: bool | None
) -> ComponentResult:
    if debt_to_equity is None or free_cash_flow_positive is None:
        return ComponentResult(
            "BALANCE_SHEET_QUALITY", 3, None, "MISSING_DATA", "missing debt/equity or FCF sign"
        )
    status = (
        "PASS"
        if debt_to_equity <= _MAX_REASONABLE_DEBT_TO_EQUITY and free_cash_flow_positive
        else "FAIL"
    )
    return ComponentResult("BALANCE_SHEET_QUALITY", 3, debt_to_equity, status, None)


def _component_4_valuation(
    pe_ratio: Decimal | None, sector_median_pe: Decimal | None, peg_ratio: Decimal | None
) -> ComponentResult:
    if pe_ratio is None and peg_ratio is None:
        return ComponentResult(
            "VALUATION", 4, None, "MISSING_DATA", "missing P/E and PEG — cannot assess valuation"
        )
    reasonable_vs_sector = (
        pe_ratio is not None and sector_median_pe is not None and pe_ratio <= sector_median_pe
    )
    reasonable_vs_growth = peg_ratio is not None and peg_ratio < _PEG_REASONABLE_MAX
    status = "PASS" if (reasonable_vs_sector or reasonable_vs_growth) else "FAIL"
    return ComponentResult(
        "VALUATION", 4, pe_ratio if pe_ratio is not None else peg_ratio, status, None
    )


def _component_5_earnings_revision_direction(direction: str | None) -> ComponentResult:
    if direction is None:
        return ComponentResult(
            "EARNINGS_REVISION_DIRECTION", 5, None, "MISSING_DATA", "no revision direction supplied"
        )
    status = "PASS" if direction == "UP" else "FAIL"
    return ComponentResult("EARNINGS_REVISION_DIRECTION", 5, None, status, direction)


def _component_6_sector_durability(sector_name: str | None) -> ComponentResult:
    if sector_name is None:
        return ComponentResult(
            "BUSINESS_SECTOR_DURABILITY",
            6,
            None,
            "MISSING_DATA",
            "no sector classification supplied",
        )
    status = "PASS" if sector_name in _DURABLE_SECTORS else "FAIL"
    return ComponentResult("BUSINESS_SECTOR_DURABILITY", 6, None, status, sector_name)


def _component_7_long_term_relative_strength(
    instrument_closes: list[Decimal | None], benchmark_closes: list[Decimal | None], as_of: date
) -> ComponentResult:
    rs = relative_strength(instrument_closes, benchmark_closes, _LONG_TERM_RS_WINDOW_DAYS, as_of)
    if rs.status != "OK" or rs.value is None:
        return ComponentResult(
            "LONG_TERM_RELATIVE_STRENGTH", 7, None, rs.status, rs.explanation_code
        )
    status = "PASS" if rs.value > 0 else "FAIL"
    return ComponentResult("LONG_TERM_RELATIVE_STRENGTH", 7, rs.value, status, None)


def _component_8_catalysts_and_event_risk(
    documented_catalyst_count: int | None, has_major_unresolved_event_risk: bool | None
) -> ComponentResult:
    if documented_catalyst_count is None:
        return ComponentResult(
            "CATALYSTS_EVENT_RISK", 8, None, "MISSING_DATA", "no catalyst count supplied"
        )
    event_risk = bool(has_major_unresolved_event_risk)
    status = "PASS" if documented_catalyst_count > 0 and not event_risk else "FAIL"
    detail = "major unresolved event risk flagged" if event_risk else None
    return ComponentResult(
        "CATALYSTS_EVENT_RISK", 8, Decimal(documented_catalyst_count), status, detail
    )


def _component_9_diversification_concentration(
    position_pct_of_portfolio: Decimal | None,
    sector_concentration_pct: Decimal | None,
    max_position_pct: Decimal,
    max_sector_pct: Decimal,
) -> ComponentResult:
    if position_pct_of_portfolio is None or sector_concentration_pct is None:
        return ComponentResult(
            "PORTFOLIO_DIVERSIFICATION",
            9,
            None,
            "MISSING_DATA",
            "missing position or sector weight",
        )
    status = (
        "PASS"
        if position_pct_of_portfolio <= max_position_pct
        and sector_concentration_pct <= max_sector_pct
        else "FAIL"
    )
    return ComponentResult("PORTFOLIO_DIVERSIFICATION", 9, position_pct_of_portfolio, status, None)


def compute_investment_quality(
    *,
    revenue_growth_yoy_pct: Decimal | None,
    earnings_growth_yoy_pct: Decimal | None,
    margin_trend_bps_yoy: Decimal | None,
    debt_to_equity: Decimal | None,
    free_cash_flow_positive: bool | None,
    pe_ratio: Decimal | None,
    sector_median_pe: Decimal | None,
    peg_ratio: Decimal | None,
    earnings_revision_direction: str | None,
    sector_name: str | None,
    instrument_closes: list[Decimal | None],
    benchmark_closes: list[Decimal | None],
    documented_catalyst_count: int | None,
    has_major_unresolved_event_risk: bool | None,
    position_pct_of_portfolio: Decimal | None,
    sector_concentration_pct: Decimal | None,
    max_position_pct: Decimal,
    max_sector_pct: Decimal,
    has_going_concern_flag: bool,
    has_unresolved_data_quality_issue: bool,
    as_of: date,
) -> InvestmentQualityResult:
    components = [
        _component_1_revenue_and_earnings_growth(revenue_growth_yoy_pct, earnings_growth_yoy_pct),
        _component_2_margin_trend(margin_trend_bps_yoy),
        _component_3_balance_sheet_quality(debt_to_equity, free_cash_flow_positive),
        _component_4_valuation(pe_ratio, sector_median_pe, peg_ratio),
        _component_5_earnings_revision_direction(earnings_revision_direction),
        _component_6_sector_durability(sector_name),
        _component_7_long_term_relative_strength(instrument_closes, benchmark_closes, as_of),
        _component_8_catalysts_and_event_risk(
            documented_catalyst_count, has_major_unresolved_event_risk
        ),
        _component_9_diversification_concentration(
            position_pct_of_portfolio, sector_concentration_pct, max_position_pct, max_sector_pct
        ),
    ]

    hard_disqualified = has_going_concern_flag or has_unresolved_data_quality_issue
    reason = None
    if has_going_concern_flag:
        reason = "going-concern flag is set"
    elif has_unresolved_data_quality_issue:
        reason = "unresolved data-quality issue on this instrument"

    return InvestmentQualityResult(
        components=components,
        hard_disqualified=hard_disqualified,
        disqualification_reason=reason,
    )
