"""Baseline eligibility gate for the tactical earnings lane (Revision
Prompt 5). An AND gate, not a score — mirrors HES-2's design exactly
(R1): every condition must pass; any single failing condition makes the
event ineligible, regardless of how strong the others are. Deliberately
takes plain, caller-supplied values rather than querying the database
itself, so it stays a pure, independently testable function — the
caller (a future ingestion/scoring job, not built this pass since "do
not create recommendations yet") is responsible for gathering the
portfolio-capacity and data-quality inputs from wherever they actually
live.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

CALCULATION_VERSION = "v1"

# Versioned thresholds (principle 8).
_MIN_DIRECTION_SCORE = 6
_MAX_DIRECTION_SCORE = 8
_MIN_EXPECTED_MOVE_PCT = Decimal(4)
_MIN_AVG_DAILY_DOLLAR_VOLUME = Decimal(50_000_000)
_MIN_ANALYST_ESTIMATES = 3
_UNVERIFIED_TIMING_CATEGORIES = frozenset({"UNKNOWN", "TIME_NOT_SUPPLIED", "DATE_UNCONFIRMED"})


@dataclass(frozen=True)
class EligibilityCondition:
    condition_key: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class BaselineEligibilityResult:
    conditions: list[EligibilityCondition]
    eligible: bool
    calculation_version: str = CALCULATION_VERSION


def evaluate_baseline_eligibility(
    *,
    direction_score: int,
    expected_move_pct: Decimal | None,
    avg_daily_dollar_volume: Decimal | None,
    num_analyst_estimates: int | None,
    timing_category: str,
    evidence_is_fresh: bool,
    has_portfolio_capacity: bool,
    has_sector_capacity: bool,
    has_unresolved_data_quality_issue: bool,
) -> BaselineEligibilityResult:
    conditions: list[EligibilityCondition] = []

    conditions.append(
        EligibilityCondition(
            "DIRECTION_SCORE",
            direction_score >= _MIN_DIRECTION_SCORE,
            f"{direction_score}/{_MAX_DIRECTION_SCORE}, needs >= {_MIN_DIRECTION_SCORE}",
        )
    )
    conditions.append(
        EligibilityCondition(
            "EXPECTED_MOVE",
            expected_move_pct is not None and expected_move_pct >= _MIN_EXPECTED_MOVE_PCT,
            (
                f"{expected_move_pct}%, needs >= {_MIN_EXPECTED_MOVE_PCT}%"
                if expected_move_pct is not None
                else "expected move is unavailable"
            ),
        )
    )
    conditions.append(
        EligibilityCondition(
            "LIQUIDITY",
            avg_daily_dollar_volume is not None
            and avg_daily_dollar_volume >= _MIN_AVG_DAILY_DOLLAR_VOLUME,
            (
                f"${avg_daily_dollar_volume:,.0f}, needs >= ${_MIN_AVG_DAILY_DOLLAR_VOLUME:,.0f}"
                if avg_daily_dollar_volume is not None
                else "average daily dollar volume is unavailable"
            ),
        )
    )
    conditions.append(
        EligibilityCondition(
            "ANALYST_COVERAGE",
            num_analyst_estimates is not None and num_analyst_estimates >= _MIN_ANALYST_ESTIMATES,
            (
                f"{num_analyst_estimates} estimate(s), needs >= {_MIN_ANALYST_ESTIMATES}"
                if num_analyst_estimates is not None
                else "analyst estimate count is unavailable"
            ),
        )
    )
    conditions.append(
        EligibilityCondition(
            "VERIFIED_EVENT_TIMING",
            timing_category not in _UNVERIFIED_TIMING_CATEGORIES,
            f"timing_category={timing_category}",
        )
    )
    conditions.append(
        EligibilityCondition("FRESH_EVIDENCE", evidence_is_fresh, f"is_fresh={evidence_is_fresh}")
    )
    conditions.append(
        EligibilityCondition(
            "PORTFOLIO_CAPACITY", has_portfolio_capacity, f"has_capacity={has_portfolio_capacity}"
        )
    )
    conditions.append(
        EligibilityCondition(
            "SECTOR_CAPACITY", has_sector_capacity, f"has_capacity={has_sector_capacity}"
        )
    )
    conditions.append(
        EligibilityCondition(
            "NO_UNRESOLVED_DATA_QUALITY_ISSUE",
            not has_unresolved_data_quality_issue,
            f"has_unresolved_issue={has_unresolved_data_quality_issue}",
        )
    )

    eligible = all(c.passed for c in conditions)
    return BaselineEligibilityResult(conditions=conditions, eligible=eligible)
