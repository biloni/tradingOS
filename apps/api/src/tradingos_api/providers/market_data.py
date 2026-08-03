"""Provider-neutral market data interface.

No concrete implementation lives here yet — Alpaca is the Phase 2 implementation
(see docs/PROVIDER_MATRIX.md and docs/DECISIONS.md ADR-002). Defining the
interface now lets Phase 2 land a concrete adapter without touching callers,
and keeps a synthetic/fake implementation possible for tests without hitting
a real vendor (project principle: fixtures, not live APIs, in the default
test suite).
"""

from datetime import date
from typing import Protocol

from pydantic import BaseModel


class MarketDataProviderNotConfigured(RuntimeError):
    """Raised when a provider is used without its required credentials set.

    Callers (e.g. the ingestion script) catch this and print a clear message
    instead of the feature crashing with an opaque error — principle 5:
    missing config is shown explicitly, not papered over.
    """


class PriceBarDTO(BaseModel):
    symbol: str
    as_of: date
    open: str
    high: str
    low: str
    close: str
    volume: int
    source: str
    fetched_at: str
    timezone: str


class MarketDataProvider(Protocol):
    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[PriceBarDTO]:
        """Return OHLCV daily bars for `symbol` in [start, end]. Never fabricates
        missing days — callers must handle gaps explicitly (principle 4/5)."""
        ...

    def get_latest_quote(self, symbol: str) -> PriceBarDTO | None:
        """Return the most recent bar, or None if unavailable/stale beyond the
        provider's freshness window. Never returns a stale value silently."""
        ...
