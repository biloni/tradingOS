"""Earnings calendar provider interface (Revision Prompt 4). A calendar
entry's `timing_category` uses the closed vocabulary
`models.enums.EarningsTimingCategory` (`BEFORE_OPEN`/`AFTER_CLOSE`/
`DURING_MARKET`/`TIME_NOT_SUPPLIED`/`DATE_UNCONFIRMED`) — a provider
that cannot supply timing must say `TIME_NOT_SUPPLIED`, never guess
`BEFORE_OPEN` as a default. `revision_id` (from the shared
`PointInTimeEnvelope`) is what `services/ingest_evidence.py` compares
against the previously-ingested `EarningsEvent` to detect a correction
and write an `EarningsEventCorrection` + `Alert` instead of a silent
overwrite.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class EarningsCalendarProviderNotConfigured(RuntimeError):
    pass


class EarningsCalendarProviderUnavailable(RuntimeError):
    pass


class EarningsCalendarCapabilities(ProviderCapabilities):
    supports_verified_date: bool
    supports_timing_category: bool
    supports_fiscal_period: bool


class EarningsCalendarRecord(PointInTimeEnvelope):
    ticker: str
    report_date: date
    fiscal_period: str | None = None
    timing_category: str
    verification_source: str | None = None


class EarningsCalendarProvider(Protocol):
    def get_capabilities(self) -> EarningsCalendarCapabilities: ...

    def get_upcoming_earnings(self, ticker: str, within_days: int) -> list[EarningsCalendarRecord]:
        """Every entry's `timing_category` must be one of the closed
        enum values — a provider record with no confirmed date at all is
        `DATE_UNCONFIRMED`, not omitted (principle 5: show uncertainty,
        don't hide it by leaving the row out)."""
        ...
