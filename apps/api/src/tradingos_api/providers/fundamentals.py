"""Fundamentals provider interface (Revision Prompt 4,
docs/BLOCKING_DECISIONS.md #1 — no vendor chosen/contracted yet)."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class FundamentalsProviderNotConfigured(RuntimeError):
    pass


class FundamentalsProviderUnavailable(RuntimeError):
    pass


class FundamentalsCapabilities(ProviderCapabilities):
    supports_market_cap: bool
    supports_pe_ratio: bool
    supports_sector_classification: bool


class FundamentalsRecord(PointInTimeEnvelope):
    ticker: str
    as_of: date
    market_cap: str | None = None
    pe_ratio: str | None = None
    sector_name: str | None = None


class FundamentalsProvider(Protocol):
    def get_capabilities(self) -> FundamentalsCapabilities: ...

    def get_fundamentals(self, ticker: str) -> FundamentalsRecord | None: ...
