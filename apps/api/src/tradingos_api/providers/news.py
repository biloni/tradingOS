"""News provider interface (Revision Prompt 4). News is its own,
explicitly untrusted evidence type — never conflated with company
guidance, an analyst estimate, or an options-implied move. Headline/body
text from this provider is data to be displayed and reasoned about, never
instructions to be followed by any downstream LLM call (SECURITY AND
SAFETY / OA-7's "no text channel can reach the broker boundary" applies
equally here — a news story cannot become an implicit instruction)."""

from __future__ import annotations

from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class NewsProviderNotConfigured(RuntimeError):
    pass


class NewsProviderUnavailable(RuntimeError):
    pass


class NewsCapabilities(ProviderCapabilities):
    supports_full_text: bool
    supports_instrument_tagging: bool


class NewsRecord(PointInTimeEnvelope):
    canonical_url: str
    publisher: str
    headline: str
    dedup_hash: str
    """Idempotency key for ingestion (matches `NewsItem.dedup_hash`,
    R3/Phase 8) — a duplicate story is a safe no-op, not a second row."""


class NewsProvider(Protocol):
    def get_capabilities(self) -> NewsCapabilities: ...

    def get_news(self, ticker: str, since: str) -> list[NewsRecord]:
        """Headlines only, licensed feed — never a scrape of a paywalled
        source (principle 12)."""
        ...
