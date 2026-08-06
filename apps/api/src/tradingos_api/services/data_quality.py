"""Data-quality gates (Revision Prompt 4) — the 9 required checks, each a
pure function returning a `DataQualityFinding | None` (never raising —
callers decide what a finding means for their own flow) so every check
is independently unit-testable without a database. `record_finding()` is
the one place a finding becomes a `DataQualityEvent` row (the same
generic subject_type/subject_id shape ADR-015 already established),
matching this codebase's existing pure-function-plus-thin-DB-writer
split (e.g. `services/audit.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from tradingos_api.models.enums import DataQualityStatus
from tradingos_api.models.market_evidence import DataQualityEvent

# A short, hardcoded list of known 2026 NYSE/NASDAQ half (early-close,
# 1:00pm ET) trading days — not exhaustive beyond this year, documented
# as a known limitation rather than pretending it's a full calendar
# service (a real market-calendar vendor is a future decision, same as
# every other undecided evidence vendor, docs/BLOCKING_DECISIONS.md).
KNOWN_EARLY_CLOSE_DATES_2026: frozenset[date] = frozenset(
    {
        date(2026, 7, 3),  # day before Independence Day
        date(2026, 11, 27),  # day after Thanksgiving
        date(2026, 12, 24),  # Christmas Eve
    }
)


@dataclass(frozen=True)
class DataQualityFinding:
    status: DataQualityStatus
    detail: str


def record_finding(
    db: Session,
    finding: DataQualityFinding,
    *,
    subject_type: str,
    subject_id: uuid.UUID | None,
    instrument_id: uuid.UUID | None,
    detected_at: datetime,
) -> DataQualityEvent:
    event = DataQualityEvent(
        subject_type=subject_type,
        subject_id=subject_id,
        instrument_id=instrument_id,
        status=finding.status,
        detail=finding.detail,
        detected_at=detected_at,
    )
    db.add(event)
    db.flush()
    return event


def check_conflicting_dates_or_timing(
    sources: list[tuple[str, date, str]],
) -> DataQualityFinding | None:
    """`sources` is `(source_name, report_date, timing_category)` per
    provider that reported this event. Flags `CONFLICTING` iff more than
    one distinct (date, timing) pair exists across sources."""
    if len(sources) < 2:
        return None
    distinct = {(report_date, timing) for _, report_date, timing in sources}
    if len(distinct) <= 1:
        return None
    named = ", ".join(f"{name}={report_date}/{timing}" for name, report_date, timing in sources)
    return DataQualityFinding(
        status=DataQualityStatus.CONFLICTING,
        detail=f"Sources disagree on earnings date/timing: {named}",
    )


def check_too_few_analysts(
    num_analysts: int | None, *, minimum: int = 3
) -> DataQualityFinding | None:
    if num_analysts is None:
        return DataQualityFinding(
            status=DataQualityStatus.MISSING, detail="Analyst count not supplied by provider."
        )
    if num_analysts < minimum:
        return DataQualityFinding(
            status=DataQualityStatus.DELAYED,
            detail=f"Only {num_analysts} analyst(s) cover this estimate (minimum {minimum}).",
        )
    return None


def check_stale_quote_or_bars(
    observed_at: datetime, *, now: datetime, max_age: timedelta
) -> DataQualityFinding | None:
    age = now - observed_at
    if age > max_age:
        return DataQualityFinding(
            status=DataQualityStatus.STALE,
            detail=f"Last observation is {age} old (max allowed {max_age}).",
        )
    return None


def check_missing_split_adjustment(
    *, bar_adjusted: bool, bar_as_of: date, split_ex_dates: list[date]
) -> DataQualityFinding | None:
    """Flags a bar as unadjusted-but-should-be-adjusted when a split's
    `ex_date` falls on or before the bar's own date and the bar itself
    was never marked `adjusted`."""
    if bar_adjusted:
        return None
    applicable = [d for d in split_ex_dates if d <= bar_as_of]
    if not applicable:
        return None
    return DataQualityFinding(
        status=DataQualityStatus.CONFLICTING,
        detail=(
            f"Bar for {bar_as_of} is not split-adjusted but a split ex-dated "
            f"{max(applicable)} applies on or before it."
        ),
    )


def check_duplicate_news(dedup_hash: str, existing_hashes: set[str]) -> DataQualityFinding | None:
    if dedup_hash in existing_hashes:
        return DataQualityFinding(
            status=DataQualityStatus.CONFLICTING,
            detail=f"News item with dedup_hash {dedup_hash} has already been ingested.",
        )
    return None


def check_symbol_mapping_conflict(validation_status: str) -> DataQualityFinding | None:
    """`validation_status` is `models.enums.InstrumentValidationStatus`'s
    value — `AMBIGUOUS` means the raw input resolved to more than one
    candidate instrument."""
    if validation_status == "AMBIGUOUS":
        return DataQualityFinding(
            status=DataQualityStatus.CONFLICTING,
            detail="Raw symbol input resolved to more than one candidate instrument.",
        )
    return None


def check_guidance_unit_or_fiscal_period_mismatch(
    *,
    guidance_units: str | None,
    guidance_period: str | None,
    expected_units: str,
    expected_fiscal_period: str,
) -> DataQualityFinding | None:
    if guidance_units is None or guidance_period is None:
        return DataQualityFinding(
            status=DataQualityStatus.MISSING,
            detail="Guidance item is missing units or fiscal period.",
        )
    if guidance_units != expected_units:
        return DataQualityFinding(
            status=DataQualityStatus.CONFLICTING,
            detail=f"Guidance units {guidance_units!r} do not match expected {expected_units!r}.",
        )
    if guidance_period != expected_fiscal_period:
        return DataQualityFinding(
            status=DataQualityStatus.CONFLICTING,
            detail=(
                f"Guidance fiscal period {guidance_period!r} does not match "
                f"the earnings event's {expected_fiscal_period!r}."
            ),
        )
    return None


def check_implied_move_timestamp_inconsistency(
    *, expected_move_as_of: datetime, planned_entry_at: datetime, max_gap: timedelta
) -> DataQualityFinding | None:
    gap = abs(planned_entry_at - expected_move_as_of)
    if gap > max_gap:
        return DataQualityFinding(
            status=DataQualityStatus.STALE,
            detail=(
                f"Options-implied expected move was captured {gap} away from the "
                f"planned entry time (max allowed {max_gap})."
            ),
        )
    return None


def check_market_calendar_early_close_mismatch(
    *, event_date: date, timing_category: str
) -> DataQualityFinding | None:
    """`DURING_MARKET` timing on a known early-close day is flagged —
    the regular-session close time shifts (1:00pm ET instead of 4:00pm
    ET) so "during market hours" is ambiguous without knowing which
    close time was assumed."""
    if event_date in KNOWN_EARLY_CLOSE_DATES_2026 and timing_category == "DURING_MARKET":
        return DataQualityFinding(
            status=DataQualityStatus.CONFLICTING,
            detail=(
                f"{event_date} is a known early-close trading day; DURING_MARKET timing "
                "is ambiguous without specifying which close time was assumed."
            ),
        )
    return None
