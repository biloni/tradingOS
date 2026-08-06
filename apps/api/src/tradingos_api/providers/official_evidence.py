"""Company guidance and official-filing provider interfaces (Revision
Prompt 4) — grouped in one file because both are source-priority-1
evidence types ("prefer official company investor-relations releases
and regulatory filings for reported results and formal guidance"), never
a journalist's interpretation or an analyst's target labeled as either.

`CompanyGuidanceRecord.source_type` is restricted to `"official_ir_release"`
or `"regulatory_filing"` at the type level — a journalist's interpretation
or an analyst's target can never be constructed as one (source-priority
requirement enforced structurally, not just by convention). That kind of
secondary commentary belongs to `NewsProvider`/`AnalystRevisionProvider`
instead.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities

GuidanceSourceType = Literal["official_ir_release", "regulatory_filing"]


class CompanyGuidanceProviderNotConfigured(RuntimeError):
    pass


class CompanyGuidanceProviderUnavailable(RuntimeError):
    pass


class CompanyGuidanceCapabilities(ProviderCapabilities):
    supports_midpoint: bool
    supports_units: bool


class CompanyGuidanceRecord(PointInTimeEnvelope):
    ticker: str
    metric: str
    period: str
    guidance_low: str | None = None
    guidance_high: str | None = None
    guidance_midpoint: str | None = None
    units: str
    source_type: GuidanceSourceType


class CompanyGuidanceProvider(Protocol):
    def get_capabilities(self) -> CompanyGuidanceCapabilities: ...

    def get_guidance(
        self, ticker: str, fiscal_period: str | None = None
    ) -> list[CompanyGuidanceRecord]:
        """Empty list, not a fabricated entry, when the company has not
        issued formal guidance for the requested period — a no-guidance
        quarter is its own explicit outcome (HES-4), not defaulted to
        anything."""
        ...


class OfficialFilingProviderNotConfigured(RuntimeError):
    pass


class OfficialFilingProviderUnavailable(RuntimeError):
    pass


class OfficialFilingCapabilities(ProviderCapabilities):
    supports_full_text_link: bool
    covered_filing_types: tuple[str, ...]


class OfficialFilingRecord(PointInTimeEnvelope):
    ticker: str
    filing_type: str
    filed_date: date
    canonical_url: str


class OfficialFilingProvider(Protocol):
    """Regulatory filings (e.g. an 8-K, 10-Q) — the other source-
    priority-1 evidence type alongside official IR releases. Never
    scrapes a paywalled source (principle 12) — every implementation
    must be backed by a licensed feed or a public regulatory filing
    index."""

    def get_capabilities(self) -> OfficialFilingCapabilities: ...

    def get_filings(self, ticker: str, since: date) -> list[OfficialFilingRecord]: ...
