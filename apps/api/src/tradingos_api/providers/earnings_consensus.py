"""Earnings consensus and analyst-revision provider interfaces
(Revision Prompt 4) — one file since both describe "what analysts
currently think," distinct from `CompanyGuidanceProvider` (what the
company itself has formally stated, never conflated with an analyst's
number or a journalist's paraphrase of one)."""

from __future__ import annotations

from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class EarningsConsensusProviderNotConfigured(RuntimeError):
    pass


class EarningsConsensusProviderUnavailable(RuntimeError):
    pass


class EarningsConsensusCapabilities(ProviderCapabilities):
    supports_revenue_consensus: bool
    supports_analyst_count: bool
    supports_dispersion: bool


class EarningsConsensusRecord(PointInTimeEnvelope):
    ticker: str
    consensus_eps: str | None = None
    consensus_revenue: str | None = None
    num_analysts: int | None = None
    eps_dispersion: str | None = None
    """Estimate dispersion — only populated when the provider actually
    supplies it (`get_capabilities().supports_dispersion`); never
    computed by this interface itself from a single point estimate."""


class EarningsConsensusProvider(Protocol):
    def get_capabilities(self) -> EarningsConsensusCapabilities: ...

    def get_consensus(self, ticker: str) -> EarningsConsensusRecord | None: ...


class AnalystRevisionProviderNotConfigured(RuntimeError):
    pass


class AnalystRevisionProviderUnavailable(RuntimeError):
    pass


class AnalystRevisionCapabilities(ProviderCapabilities):
    supports_configurable_windows: bool
    default_windows_days: tuple[int, ...] = (7, 30, 90)


class AnalystRevisionRecord(PointInTimeEnvelope):
    ticker: str
    revised_at: str
    previous_eps_estimate: str | None = None
    new_eps_estimate: str
    direction: str


class AnalystRevisionProvider(Protocol):
    def get_capabilities(self) -> AnalystRevisionCapabilities: ...

    def get_revisions(self, ticker: str, window_days: int) -> list[AnalystRevisionRecord]:
        """`window_days` is caller-configurable (7/30/90 are the
        required windows, docs/PROMPT_4 ingestion spec) — the provider
        adapter itself does not hardcode a window."""
        ...
