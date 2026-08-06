"""Market quote and historical bars provider interfaces (Revision
Prompt 4). Split from the shipped-MVP `providers/market_data.py`
(unchanged, still used by the Phase 1-7-descended ingestion path) into
two precisely-named interfaces so a caller that only needs a quote never
depends on bars-fetching capability, and vice versa — the "one vendor
may implement several interfaces" case this revision explicitly allows.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class MarketQuoteProviderNotConfigured(RuntimeError):
    pass


class MarketQuoteProviderUnavailable(RuntimeError):
    pass


class MarketQuoteCapabilities(ProviderCapabilities):
    is_real_time: bool
    supports_extended_hours: bool


class QuoteRecord(PointInTimeEnvelope):
    ticker: str
    price: str
    volume: int | None = None


class MarketQuoteProvider(Protocol):
    def get_capabilities(self) -> MarketQuoteCapabilities: ...

    def get_latest_quote(self, ticker: str) -> QuoteRecord | None:
        """Never returns a stale value silently — `None` if unavailable
        within the provider's own freshness window (principle 5); the
        caller's own staleness gate (`services/data_quality.py`) applies
        on top of whatever this returns."""
        ...


class HistoricalBarsProviderNotConfigured(RuntimeError):
    pass


class HistoricalBarsProviderUnavailable(RuntimeError):
    pass


class HistoricalBarsCapabilities(ProviderCapabilities):
    supports_split_adjustment: bool
    supports_dividend_adjustment: bool
    max_lookback_days: int | None = None


class BarRecord(PointInTimeEnvelope):
    ticker: str
    as_of: date
    open: str
    high: str
    low: str
    close: str
    volume: int
    adjusted: bool


class HistoricalBarsProvider(Protocol):
    def get_capabilities(self) -> HistoricalBarsCapabilities: ...

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[BarRecord]:
        """Never fabricates missing days — callers must handle gaps
        explicitly (principle 4/5)."""
        ...
