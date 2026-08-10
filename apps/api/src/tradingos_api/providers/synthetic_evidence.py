"""Synthetic, fixture-backed implementations of the 8 Revision Prompt 4
interfaces Alpaca's free tier cannot serve (fundamentals, earnings
calendar/consensus/revisions, company guidance, official filings, macro,
options-implied move — docs/BLOCKING_DECISIONS.md #1/#2, still open, no
vendor contracted). "Do not purchase a paid service" is this revision's
own explicit instruction — every class here is honest about
`is_live_data=False` via its capability response, never disguised as a
real vendor call. Data is small, curated, and deterministic (no RNG),
matching `scripts/seed_phase8.py`'s existing discipline.

`SyntheticCompanyGuidanceProvider` is the one class that does real
parsing work rather than a fixture lookup: it stores a synthetic official
investor-relations press-release *string* per (ticker, period) and
extracts metric/period/low/high/midpoint/units from it with
`_parse_guidance_release()` — demonstrating the "guidance parsing with
synthetic official releases" requirement structurally, not just as a
canned return value.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tradingos_api.providers.company_guidance_release_fixtures import (
    SYNTHETIC_GUIDANCE_RELEASES,
)
from tradingos_api.providers.earnings_actuals import (
    EarningsActualRecord,
    EarningsActualsCapabilities,
)
from tradingos_api.providers.earnings_calendar import (
    EarningsCalendarCapabilities,
    EarningsCalendarRecord,
)
from tradingos_api.providers.earnings_consensus import (
    AnalystRevisionCapabilities,
    AnalystRevisionRecord,
    EarningsConsensusCapabilities,
    EarningsConsensusRecord,
)
from tradingos_api.providers.fundamentals import FundamentalsCapabilities, FundamentalsRecord
from tradingos_api.providers.macro import MacroCapabilities, MacroObservationRecord
from tradingos_api.providers.official_evidence import (
    CompanyGuidanceCapabilities,
    CompanyGuidanceRecord,
    OfficialFilingCapabilities,
    OfficialFilingRecord,
)
from tradingos_api.providers.options_expected_move import (
    OptionsExpectedMoveCapabilities,
    OptionsExpectedMoveRecord,
)

_SOURCE = "synthetic_fixture"


class SyntheticFundamentalsProvider:
    """Fixture keyed by ticker — a small, curated set covering the demo
    symbols this project already seeds (`scripts/seed_phase8.py`)."""

    _FIXTURES: dict[str, dict[str, str]] = {
        "AAPL": {"market_cap": "3200000000000.00", "pe_ratio": "31.4000", "sector": "Technology"},
        "AMD": {"market_cap": "280000000000.00", "pe_ratio": "45.2000", "sector": "Technology"},
        "MRVL": {"market_cap": "75000000000.00", "pe_ratio": "38.1000", "sector": "Technology"},
        "TSLA": {"market_cap": "780000000000.00", "pe_ratio": "62.0000", "sector": "Technology"},
    }

    def get_capabilities(self) -> FundamentalsCapabilities:
        return FundamentalsCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            supports_market_cap=True,
            supports_pe_ratio=True,
            supports_sector_classification=True,
        )

    def get_fundamentals(self, ticker: str) -> FundamentalsRecord | None:
        row = self._FIXTURES.get(ticker.upper())
        if row is None:
            return None
        now = datetime.now(UTC)
        return FundamentalsRecord(
            published_at=now,
            observed_at=now,
            source=_SOURCE,
            ticker=ticker.upper(),
            as_of=now.date(),
            market_cap=row["market_cap"],
            pe_ratio=row["pe_ratio"],
            sector_name=row["sector"],
        )


class SyntheticEarningsCalendarProvider:
    """Fixture upcoming-earnings calendar. `AMD` deliberately mirrors the
    R3 seed data's own upcoming AMD earnings event so an ingestion demo
    run and the seed data tell the same story."""

    _FIXTURES: dict[str, dict[str, str]] = {
        "AMD": {
            "report_date": "2026-08-13",
            "fiscal_period": "Q3-2026",
            "timing_category": "AFTER_CLOSE",
        },
        "TSLA": {
            "report_date": "2026-08-07",
            "fiscal_period": "Q3-2026",
            "timing_category": "TIME_NOT_SUPPLIED",
        },
    }

    def get_capabilities(self) -> EarningsCalendarCapabilities:
        return EarningsCalendarCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            supports_verified_date=True,
            supports_timing_category=True,
            supports_fiscal_period=True,
        )

    def get_upcoming_earnings(self, ticker: str, within_days: int) -> list[EarningsCalendarRecord]:
        row = self._FIXTURES.get(ticker.upper())
        if row is None:
            return []
        now = datetime.now(UTC)
        return [
            EarningsCalendarRecord(
                published_at=now,
                observed_at=now,
                source=_SOURCE,
                revision_id="v1",
                ticker=ticker.upper(),
                report_date=date.fromisoformat(row["report_date"]),
                fiscal_period=row["fiscal_period"],
                timing_category=row["timing_category"],
                verification_source="synthetic_ir_calendar_fixture",
            )
        ]


class SyntheticEarningsConsensusProvider:
    _FIXTURES: dict[str, dict[str, object]] = {
        "AMD": {
            "consensus_eps": "1.1500",
            "consensus_revenue": "8200000000.00",
            "num_analysts": 32,
            "eps_dispersion": "0.0800",
        },
    }

    def get_capabilities(self) -> EarningsConsensusCapabilities:
        return EarningsConsensusCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            supports_revenue_consensus=True,
            supports_analyst_count=True,
            supports_dispersion=True,
        )

    def get_consensus(self, ticker: str) -> EarningsConsensusRecord | None:
        row = self._FIXTURES.get(ticker.upper())
        if row is None:
            return None
        now = datetime.now(UTC)
        return EarningsConsensusRecord(
            published_at=now,
            observed_at=now,
            source=_SOURCE,
            ticker=ticker.upper(),
            consensus_eps=str(row["consensus_eps"]),
            consensus_revenue=str(row["consensus_revenue"]),
            num_analysts=int(row["num_analysts"]),  # type: ignore[call-overload]
            eps_dispersion=str(row["eps_dispersion"]),
        )


class SyntheticAnalystRevisionProvider:
    """One synthetic revision history for AMD, spread across the three
    required windows (7/30/90 days) relative to a fixed reference `now`
    so `get_revisions(window_days=N)` returns a different, correct subset
    per window — not the same list regardless of `window_days`."""

    _REFERENCE_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    _REVISIONS: list[dict[str, object]] = [
        {"days_ago": 3, "previous": "1.1000", "new": "1.1500", "direction": "UP"},
        {"days_ago": 20, "previous": "1.0500", "new": "1.1000", "direction": "UP"},
        {"days_ago": 60, "previous": "1.1200", "new": "1.0500", "direction": "DOWN"},
        {"days_ago": 85, "previous": "1.0800", "new": "1.1200", "direction": "UP"},
    ]

    def get_capabilities(self) -> AnalystRevisionCapabilities:
        return AnalystRevisionCapabilities(
            provider_name=_SOURCE, is_live_data=False, supports_configurable_windows=True
        )

    def get_revisions(self, ticker: str, window_days: int) -> list[AnalystRevisionRecord]:
        if ticker.upper() != "AMD":
            return []

        records: list[AnalystRevisionRecord] = []
        for row in self._REVISIONS:
            days_ago = int(row["days_ago"])  # type: ignore[call-overload]
            if days_ago > window_days:
                continue
            revised_at = self._REFERENCE_NOW - timedelta(days=days_ago)
            records.append(
                AnalystRevisionRecord(
                    published_at=revised_at,
                    observed_at=revised_at,
                    source=_SOURCE,
                    ticker="AMD",
                    revised_at=revised_at.isoformat(),
                    previous_eps_estimate=str(row["previous"]),
                    new_eps_estimate=str(row["new"]),
                    direction=str(row["direction"]),
                )
            )
        return records


class SyntheticEarningsActualsProvider:
    """Fixture reported results for AMD's Q3-2026 event — a deliberate
    beat on both metrics (EPS 1.2200 vs. `SyntheticEarningsConsensusProvider`'s
    consensus_eps 1.1500; revenue 8.35B vs. consensus 8.2B) so the post-
    earnings confirmation demo has a real positive surprise to score
    against, consistent with the AMD fixtures already shared across the
    calendar/consensus/revision providers above."""

    _FIXTURES: dict[str, dict[str, dict[str, str]]] = {
        "AMD": {
            "Q3-2026": {"eps": "1.2200", "revenue": "8350000000.00"},
        },
    }

    def get_capabilities(self) -> EarningsActualsCapabilities:
        return EarningsActualsCapabilities(
            provider_name=_SOURCE, is_live_data=False, supports_revenue_actual=True
        )

    def get_actuals(self, ticker: str, fiscal_period: str) -> list[EarningsActualRecord]:
        row = self._FIXTURES.get(ticker.upper(), {}).get(fiscal_period)
        if row is None:
            return []
        now = datetime.now(UTC)
        return [
            EarningsActualRecord(
                published_at=now,
                observed_at=now,
                source=_SOURCE,
                ticker=ticker.upper(),
                fiscal_period=fiscal_period,
                metric=metric,
                actual_value=value,
                source_type="official_ir_release",
            )
            for metric, value in row.items()
        ]


def _parse_guidance_release(release_text: str) -> CompanyGuidanceRecord:
    """Extracts metric/period/low/high/units from a synthetic official
    IR release string, e.g.:
    'For Q3 2026, the Company expects revenue in the range of $8.0
    billion to $8.4 billion.' -> metric=revenue, period=Q3-2026,
    low=8000000000, high=8400000000, units=USD.

    Deliberately a real (if narrow) parser, not a lookup table — this is
    what the "guidance parsing with synthetic official releases" test
    exercises. A release that doesn't match the expected shape raises
    `ValueError` rather than guessing (principle 4)."""
    period_match = re.search(r"For (Q\d) (\d{4})", release_text)
    metric_match = re.search(r"expects (\w+) in the range of", release_text)
    range_match = re.search(r"\$([\d.]+) billion to \$([\d.]+) billion", release_text)
    if not (period_match and metric_match and range_match):
        raise ValueError(f"Could not parse guidance release: {release_text!r}")

    period = f"{period_match.group(1)}-{period_match.group(2)}"
    metric = metric_match.group(1)
    low = Decimal(range_match.group(1)) * Decimal("1000000000")
    high = Decimal(range_match.group(2)) * Decimal("1000000000")
    midpoint = (low + high) / 2

    now = datetime.now(UTC)
    return CompanyGuidanceRecord(
        published_at=now,
        observed_at=now,
        source=_SOURCE,
        metric=metric,
        period=period,
        guidance_low=str(low),
        guidance_high=str(high),
        guidance_midpoint=str(midpoint),
        units="USD",
        source_type="official_ir_release",
        ticker="",
    )


class SyntheticCompanyGuidanceProvider:
    """Parses `SYNTHETIC_GUIDANCE_RELEASES` (synthetic official IR
    release text, `providers/company_guidance_release_fixtures.py`) with
    `_parse_guidance_release()` rather than returning a canned dict."""

    def get_capabilities(self) -> CompanyGuidanceCapabilities:
        return CompanyGuidanceCapabilities(
            provider_name=_SOURCE, is_live_data=False, supports_midpoint=True, supports_units=True
        )

    def get_guidance(
        self, ticker: str, fiscal_period: str | None = None
    ) -> list[CompanyGuidanceRecord]:
        release_text = SYNTHETIC_GUIDANCE_RELEASES.get(ticker.upper())
        if release_text is None:
            return []
        record = _parse_guidance_release(release_text)
        record = record.model_copy(update={"ticker": ticker.upper()})
        if fiscal_period is not None and record.period != fiscal_period:
            return []
        return [record]


class SyntheticOfficialFilingProvider:
    _FIXTURES: dict[str, list[dict[str, str]]] = {
        "AMD": [
            {
                "filing_type": "8-K",
                "filed_date": "2026-08-13",
                "canonical_url": "https://example-sec.test/AMD/8-K/2026-08-13",
            }
        ],
    }

    def get_capabilities(self) -> OfficialFilingCapabilities:
        return OfficialFilingCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            supports_full_text_link=True,
            covered_filing_types=("8-K", "10-Q", "10-K"),
        )

    def get_filings(self, ticker: str, since: date) -> list[OfficialFilingRecord]:
        rows = self._FIXTURES.get(ticker.upper(), [])
        now = datetime.now(UTC)
        return [
            OfficialFilingRecord(
                published_at=now,
                observed_at=now,
                source=_SOURCE,
                ticker=ticker.upper(),
                filing_type=row["filing_type"],
                filed_date=date.fromisoformat(row["filed_date"]),
                canonical_url=row["canonical_url"],
            )
            for row in rows
            if date.fromisoformat(row["filed_date"]) >= since
        ]


class SyntheticMacroProvider:
    """Covers macro series beyond the VIX-proxy `VolatilityIndexProvider`
    already handles via Alpaca — e.g. breadth, a synthetic macro series
    fixture until a real macro vendor is contracted (BLOCKING_DECISIONS.md
    #2)."""

    _SERIES: dict[str, list[tuple[str, str]]] = {
        "BREADTH_PCT_ABOVE_SMA50": [("2026-08-04", "0.6200"), ("2026-08-05", "0.6100")],
    }

    def get_capabilities(self) -> MacroCapabilities:
        return MacroCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            covered_series_codes=tuple(self._SERIES.keys()),
        )

    def get_series(self, series_code: str, start: date, end: date) -> list[MacroObservationRecord]:
        rows = self._SERIES.get(series_code, [])
        now = datetime.now(UTC)
        return [
            MacroObservationRecord(
                published_at=now,
                observed_at=now,
                source=_SOURCE,
                series_code=series_code,
                as_of=as_of,
                value=value,
            )
            for as_of_str, value in rows
            if start <= (as_of := date.fromisoformat(as_of_str)) <= end
        ]


class SyntheticOptionsExpectedMoveProvider:
    """`is_available=False` — no real options-chain access exists this
    pass (honest capability, not a disguised real vendor); the one fixed
    fixture value exists only so `services/data_quality.py`'s "implied
    move timestamp inconsistent with planned entry" gate has something
    concrete to test against."""

    _FIXTURES: dict[str, dict[str, str]] = {
        "AMD": {"expected_move_pct": "6.8000", "reference_event_date": "2026-08-13"},
    }

    def get_capabilities(self) -> OptionsExpectedMoveCapabilities:
        return OptionsExpectedMoveCapabilities(
            provider_name=_SOURCE, is_live_data=False, is_available=True
        )

    def get_expected_move(
        self, ticker: str, reference_event_date: str
    ) -> OptionsExpectedMoveRecord | None:
        row = self._FIXTURES.get(ticker.upper())
        if row is None or row["reference_event_date"] != reference_event_date:
            return None
        now = datetime.now(UTC)
        return OptionsExpectedMoveRecord(
            published_at=now,
            observed_at=now,
            source=_SOURCE,
            ticker=ticker.upper(),
            expected_move_pct=row["expected_move_pct"],
            reference_event_date=row["reference_event_date"],
        )


__all__ = [
    "SyntheticAnalystRevisionProvider",
    "SyntheticCompanyGuidanceProvider",
    "SyntheticEarningsCalendarProvider",
    "SyntheticEarningsConsensusProvider",
    "SyntheticFundamentalsProvider",
    "SyntheticMacroProvider",
    "SyntheticOfficialFilingProvider",
    "SyntheticOptionsExpectedMoveProvider",
]
