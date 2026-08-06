"""Instrument reference and corporate-actions provider interfaces
(Revision Prompt 4). Both describe *structural* facts about an
instrument (what it canonically is, what has structurally happened to
it) rather than a price/estimate/opinion — kept in one file because
they're the two "reference data" interfaces, not because they share
implementation.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class InstrumentReferenceProviderNotConfigured(RuntimeError):
    """Raised when an `InstrumentReferenceProvider` is used without its
    required credentials/config set."""


class InstrumentReferenceProviderUnavailable(RuntimeError):
    """Raised on a transient provider failure (timeout, rate limit, 5xx)
    — distinct from `NotConfigured` so a caller can tell "we never had
    access" from "we have access but the call failed this time" (the
    latter is what the "provider outage" test exercises)."""


class InstrumentReferenceCapabilities(ProviderCapabilities):
    supports_alias_resolution: bool
    supports_asset_type_filter: bool
    covers_otc_listings: bool


class InstrumentReferenceRecord(PointInTimeEnvelope):
    ticker: str
    name: str
    exchange: str
    asset_type: str
    active: bool


class InstrumentReferenceProvider(Protocol):
    """Resolves a raw ticker string to canonical reference data — "could
    this system ever place a paper/live order against this ticker"
    (docs/PROVIDER_MATRIX.md's symbol-reference recommendation). Symbol
    quarantine/ambiguity itself is decided by the caller
    (`InstrumentValidationEvent`, ADR-032) from this provider's answer,
    not by the provider."""

    def get_capabilities(self) -> InstrumentReferenceCapabilities: ...

    def resolve(self, raw_ticker: str) -> InstrumentReferenceRecord | None:
        """Return the canonical record for `raw_ticker`, or `None` if it
        does not resolve to exactly one tradable instrument — never a
        best guess (principle 4)."""
        ...


class CorporateActionsProviderNotConfigured(RuntimeError):
    pass


class CorporateActionsProviderUnavailable(RuntimeError):
    pass


class CorporateActionsCapabilities(ProviderCapabilities):
    supports_splits: bool
    supports_dividends: bool
    supports_mergers_spinoffs: bool


class CorporateActionRecord(PointInTimeEnvelope):
    action_type: str
    ex_date: date
    ratio: str | None = None
    amount: str | None = None


class CorporateActionsProvider(Protocol):
    """Feeds `models.market_evidence.CorporateAction`. Never invents a
    ratio/amount it wasn't given (principle 4) — a corporate action with
    an unresolved ratio is reported with `ratio=None`, not `1.0`."""

    def get_capabilities(self) -> CorporateActionsCapabilities: ...

    def get_corporate_actions(
        self, ticker: str, start: date, end: date
    ) -> list[CorporateActionRecord]: ...
