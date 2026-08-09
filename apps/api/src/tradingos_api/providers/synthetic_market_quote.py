"""Deterministic, fixture-backed `MarketQuoteProvider` (Revision Prompt
10) — the same "graceful, honest degradation without a paid vendor"
pattern as `providers/synthetic_paper_broker.py`, for the one remaining
piece the order-execution flow needs a quote for
(`services/order_execution.py::refresh_and_recalculate()`) when no
Alpaca market-data credentials are configured. `is_live_data=False`
always — never disguised as a real quote.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingos_api.providers.quotes_bars import MarketQuoteCapabilities, QuoteRecord

_SOURCE = "synthetic_fixture"
_DEFAULT_PRICE = Decimal("100.00")


class SyntheticMarketQuoteProvider:
    def __init__(self, *, reference_prices: dict[str, Decimal] | None = None) -> None:
        self._reference_prices = reference_prices or {}

    def get_capabilities(self) -> MarketQuoteCapabilities:
        return MarketQuoteCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            is_real_time=False,
            supports_extended_hours=False,
        )

    def get_latest_quote(self, ticker: str) -> QuoteRecord | None:
        now = datetime.now(UTC)
        price = self._reference_prices.get(ticker.upper(), _DEFAULT_PRICE)
        return QuoteRecord(
            published_at=None,
            observed_at=now,
            source=_SOURCE,
            ticker=ticker.upper(),
            price=str(price),
            volume=None,
        )
