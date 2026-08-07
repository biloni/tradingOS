"""The tactical earnings 8-component direction score (Revision Prompt
5, docs/HYBRID_EARNINGS_STRATEGY.md HES-1). Deterministic, versioned,
never an LLM's self-rating (principle 6/7, DQ-4/DQ-5). Each of the 8
components is scored independently as `PASS`/`FAIL`/`MISSING_DATA`/
`INSUFFICIENT_HISTORY` — `total_score` is a literal count of `PASS`
components out of 8, matching "at least 6/8" verbatim rather than a
weighted blend.

All series inputs are oldest-to-newest `list[Decimal | None]`, matching
`services/analytics.py`'s convention.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tradingos_api.services.analytics import ema, momentum, relative_strength, rolling_volume
from tradingos_api.services.scoring_common import ComponentResult

CALCULATION_VERSION = "v1"

# Component 6's threshold — "at least four analyst estimates for a
# full-quality point" (principle 8: versioned, not a buried literal).
_FULL_QUALITY_ANALYST_MINIMUM = 4

# Component 4's documented volume-accumulation rule: the trailing 5-
# session average volume exceeds the preceding 20-session average
# (excluding the 5 most recent sessions) — a simple, stated rule rather
# than an opaque OBV blend.
_VOLUME_ACCUMULATION_RECENT_WINDOW = 5
_VOLUME_ACCUMULATION_BASELINE_WINDOW = 20


@dataclass(frozen=True)
class TacticalScoreResult:
    components: list[ComponentResult]
    total_score: int
    max_score: int
    calculation_version: str = CALCULATION_VERSION


def _component_1_price_above_ema20(
    instrument_closes: list[Decimal | None], as_of: date
) -> ComponentResult:
    ema20 = ema(instrument_closes, 20, as_of)
    if ema20.status != "OK" or ema20.value is None:
        return ComponentResult("PRICE_ABOVE_EMA20", 1, None, ema20.status, ema20.explanation_code)
    latest = next((c for c in reversed(instrument_closes) if c is not None), None)
    if latest is None:
        return ComponentResult("PRICE_ABOVE_EMA20", 1, None, "MISSING_DATA", "no recent close")
    pct_above = ((latest - ema20.value) / ema20.value) * Decimal(100)
    status = "PASS" if latest > ema20.value else "FAIL"
    return ComponentResult("PRICE_ABOVE_EMA20", 1, pct_above, status, None)


def _component_2_relative_strength_20d(
    instrument_closes: list[Decimal | None], spy_closes: list[Decimal | None], as_of: date
) -> ComponentResult:
    rs = relative_strength(instrument_closes, spy_closes, 20, as_of)
    if rs.status != "OK" or rs.value is None:
        return ComponentResult("RS_20D_VS_SPY", 2, None, rs.status, rs.explanation_code)
    status = "PASS" if rs.value > 0 else "FAIL"
    return ComponentResult("RS_20D_VS_SPY", 2, rs.value, status, None)


def _component_3_momentum_5d(
    instrument_closes: list[Decimal | None], as_of: date
) -> ComponentResult:
    mom = momentum(instrument_closes, 5, as_of)
    if mom.status != "OK" or mom.value is None:
        return ComponentResult("MOMENTUM_5D", 3, None, mom.status, mom.explanation_code)
    status = "PASS" if mom.value > 0 else "FAIL"
    return ComponentResult("MOMENTUM_5D", 3, mom.value, status, None)


def _component_4_volume_accumulation(
    instrument_volumes: list[int | None], as_of: date
) -> ComponentResult:
    """Documented rule: trailing 5-session average volume > the
    preceding (non-overlapping) 20-session average volume."""
    required = _VOLUME_ACCUMULATION_RECENT_WINDOW + _VOLUME_ACCUMULATION_BASELINE_WINDOW
    if len(instrument_volumes) < required:
        return ComponentResult(
            "VOLUME_ACCUMULATION",
            4,
            None,
            "INSUFFICIENT_HISTORY",
            f"requires {required} sessions, got {len(instrument_volumes)}",
        )
    baseline_slice = instrument_volumes[-required:-_VOLUME_ACCUMULATION_RECENT_WINDOW]
    recent = rolling_volume(instrument_volumes, _VOLUME_ACCUMULATION_RECENT_WINDOW, as_of)
    baseline = rolling_volume(baseline_slice, _VOLUME_ACCUMULATION_BASELINE_WINDOW, as_of)
    if recent.status != "OK" or baseline.status != "OK":
        return ComponentResult(
            "VOLUME_ACCUMULATION", 4, None, "MISSING_DATA", "a volume in the window is missing"
        )
    assert recent.value is not None and baseline.value is not None
    delta = recent.value - baseline.value
    status = "PASS" if recent.value > baseline.value else "FAIL"
    return ComponentResult(
        "VOLUME_ACCUMULATION",
        4,
        delta,
        status,
        f"recent {_VOLUME_ACCUMULATION_RECENT_WINDOW}d avg vs prior "
        f"{_VOLUME_ACCUMULATION_BASELINE_WINDOW}d avg",
    )


def _component_5_forecast_eps_growth(
    consensus_eps_estimate: Decimal | None, prior_year_actual_eps: Decimal | None
) -> ComponentResult:
    if consensus_eps_estimate is None or prior_year_actual_eps is None:
        return ComponentResult(
            "FORECAST_EPS_GROWTH",
            5,
            None,
            "MISSING_DATA",
            "missing consensus estimate or prior-year actual",
        )
    if prior_year_actual_eps == 0:
        return ComponentResult(
            "FORECAST_EPS_GROWTH", 5, None, "MISSING_DATA", "prior-year actual EPS is zero"
        )
    growth = (
        (consensus_eps_estimate - prior_year_actual_eps) / abs(prior_year_actual_eps)
    ) * Decimal(100)
    status = "PASS" if growth > 0 else "FAIL"
    return ComponentResult("FORECAST_EPS_GROWTH", 5, growth, status, None)


def _component_6_analyst_coverage(num_analysts: int | None) -> ComponentResult:
    if num_analysts is None or num_analysts == 0:
        return ComponentResult(
            "ANALYST_COVERAGE", 6, None, "MISSING_DATA", "no analyst estimate count supplied"
        )
    status = "PASS" if num_analysts >= _FULL_QUALITY_ANALYST_MINIMUM else "FAIL"
    detail = (
        None
        if status == "PASS"
        else (
            f"only {num_analysts} analyst(s) — fewer than "
            f"{_FULL_QUALITY_ANALYST_MINIMUM} reduces completeness"
        )
    )
    return ComponentResult("ANALYST_COVERAGE", 6, Decimal(num_analysts), status, detail)


def _component_7_spy_above_ema20(spy_closes: list[Decimal | None], as_of: date) -> ComponentResult:
    ema20 = ema(spy_closes, 20, as_of)
    if ema20.status != "OK" or ema20.value is None:
        return ComponentResult("SPY_ABOVE_EMA20", 7, None, ema20.status, ema20.explanation_code)
    latest = next((c for c in reversed(spy_closes) if c is not None), None)
    if latest is None:
        return ComponentResult("SPY_ABOVE_EMA20", 7, None, "MISSING_DATA", "no recent SPY close")
    pct_above = ((latest - ema20.value) / ema20.value) * Decimal(100)
    status = "PASS" if latest > ema20.value else "FAIL"
    return ComponentResult("SPY_ABOVE_EMA20", 7, pct_above, status, None)


def _component_8_prior_gap_bias(prior_gap_pcts: list[Decimal]) -> ComponentResult:
    if len(prior_gap_pcts) < 2:
        return ComponentResult(
            "PRIOR_GAP_BIAS",
            8,
            None,
            "INSUFFICIENT_HISTORY",
            f"requires at least 2 prior earnings gaps, got {len(prior_gap_pcts)}",
        )
    median_gap = Decimal(str(statistics.median(prior_gap_pcts)))
    status = "PASS" if median_gap > 0 else "FAIL"
    return ComponentResult("PRIOR_GAP_BIAS", 8, median_gap, status, None)


def compute_tactical_earnings_score(
    *,
    instrument_closes: list[Decimal | None],
    spy_closes: list[Decimal | None],
    instrument_volumes: list[int | None],
    consensus_eps_estimate: Decimal | None,
    prior_year_actual_eps: Decimal | None,
    num_analysts: int | None,
    prior_gap_pcts: list[Decimal],
    as_of: date,
) -> TacticalScoreResult:
    components = [
        _component_1_price_above_ema20(instrument_closes, as_of),
        _component_2_relative_strength_20d(instrument_closes, spy_closes, as_of),
        _component_3_momentum_5d(instrument_closes, as_of),
        _component_4_volume_accumulation(instrument_volumes, as_of),
        _component_5_forecast_eps_growth(consensus_eps_estimate, prior_year_actual_eps),
        _component_6_analyst_coverage(num_analysts),
        _component_7_spy_above_ema20(spy_closes, as_of),
        _component_8_prior_gap_bias(prior_gap_pcts),
    ]
    total_score = sum(1 for c in components if c.status == "PASS")
    return TacticalScoreResult(components=components, total_score=total_score, max_score=8)
