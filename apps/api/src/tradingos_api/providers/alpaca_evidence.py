"""Alpaca-backed implementations of 7 of Revision Prompt 4's 15 provider
interfaces — the "one vendor may implement several interfaces" case,
each conforming to its own Protocol with its own capability/failure
types (`providers/reference_data.py`, `providers/quotes_bars.py`,
`providers/news.py`, `providers/macro.py`, `providers/broker_capability.py`).

Alpaca is the only real, contracted vendor this project has
(docs/PROVIDER_MATRIX.md, ADR-002) — every interface below that Alpaca's
free/paper tier can genuinely serve is implemented for real; everything
else is `providers/synthetic_evidence.py` instead ("do not purchase a
paid service" — Revision Prompt 4's own instruction).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

from alpaca.data.enums import Adjustment
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.models.bars import BarSet
from alpaca.data.models.corporate_actions import CorporateActionsSet
from alpaca.data.models.news import News, NewsSet
from alpaca.data.requests import (
    CorporateActionsRequest,
    NewsRequest,
    StockBarsRequest,
    StockLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.models import Asset, TradeAccount

from tradingos_api.core.config import Settings
from tradingos_api.providers.broker_capability import (
    BrokerCapabilities,
    BrokerCapabilityProviderNotConfigured,
)
from tradingos_api.providers.macro import (
    VolatilityIndexCapabilities,
    VolatilityIndexProviderNotConfigured,
    VolatilityIndexProviderUnavailable,
    VolatilityIndexRecord,
)
from tradingos_api.providers.news import NewsCapabilities, NewsProviderNotConfigured, NewsRecord
from tradingos_api.providers.quotes_bars import (
    BarRecord,
    HistoricalBarsCapabilities,
    MarketQuoteCapabilities,
    MarketQuoteProviderNotConfigured,
    QuoteRecord,
)
from tradingos_api.providers.reference_data import (
    CorporateActionRecord,
    CorporateActionsCapabilities,
    CorporateActionsProviderNotConfigured,
    InstrumentReferenceCapabilities,
    InstrumentReferenceProviderNotConfigured,
    InstrumentReferenceRecord,
)

_SOURCE = "alpaca"

# Alpaca's plural corporate-action-set keys -> this project's closed
# CorporateActionType vocabulary (models/enums.py). Any key not listed
# here (e.g. "name_changes", "redemptions") is skipped, not guessed.
_CORPORATE_ACTION_TYPE_MAP: dict[str, str] = {
    "forward_splits": "SPLIT",
    "reverse_splits": "SPLIT",
    "unit_splits": "SPLIT",
    "cash_dividends": "DIVIDEND",
    "stock_dividends": "DIVIDEND",
    "spin_offs": "SPINOFF",
    "cash_mergers": "MERGER",
    "stock_mergers": "MERGER",
    "stock_and_cash_mergers": "MERGER",
}


def _require_credentials(settings: Settings, exc_cls: type[Exception]) -> None:
    if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
        raise exc_cls(
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set. "
            "See README.md for how to obtain a free Alpaca account."
        )


class AlpacaInstrumentReferenceProvider:
    """`InstrumentReferenceProvider` backed by `TradingClient.get_asset()`
    — the same asset-reference endpoint docs/PROVIDER_MATRIX.md's symbol-
    reference recommendation names."""

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, InstrumentReferenceProviderNotConfigured)
        self._client = TradingClient(
            api_key=settings.alpaca_api_key_id,
            secret_key=settings.alpaca_api_secret_key,
            paper=True,
        )

    def get_capabilities(self) -> InstrumentReferenceCapabilities:
        return InstrumentReferenceCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            supports_alias_resolution=False,
            supports_asset_type_filter=True,
            covers_otc_listings=False,
        )

    def resolve(self, raw_ticker: str) -> InstrumentReferenceRecord | None:
        try:
            asset = self._client.get_asset(raw_ticker.upper())
        except Exception:
            return None
        if not isinstance(asset, Asset):
            return None
        now = datetime.now(UTC)
        return InstrumentReferenceRecord(
            published_at=None,
            observed_at=now,
            source=_SOURCE,
            provider_record_id=str(asset.id),
            ticker=asset.symbol,
            name=asset.name,
            exchange=asset.exchange.value,
            asset_type=asset.asset_class.value,
            active=asset.tradable,
        )


class AlpacaCorporateActionsProvider:
    """`CorporateActionsProvider` backed by Alpaca's Corporate Actions API."""

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, CorporateActionsProviderNotConfigured)
        self._client = CorporateActionsClient(
            api_key=settings.alpaca_api_key_id, secret_key=settings.alpaca_api_secret_key
        )

    def get_capabilities(self) -> CorporateActionsCapabilities:
        return CorporateActionsCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            supports_splits=True,
            supports_dividends=True,
            supports_mergers_spinoffs=True,
        )

    def get_corporate_actions(
        self, ticker: str, start: date, end: date
    ) -> list[CorporateActionRecord]:
        request = CorporateActionsRequest(symbols=[ticker.upper()], start=start, end=end)
        result = self._client.get_corporate_actions(request)
        assert isinstance(result, CorporateActionsSet)
        now = datetime.now(UTC)
        records: list[CorporateActionRecord] = []
        for raw_type, actions in result.data.items():
            mapped_type = _CORPORATE_ACTION_TYPE_MAP.get(raw_type)
            if mapped_type is None:
                continue
            for action in actions:
                ex_date = getattr(action, "ex_date", None) or getattr(
                    action, "effective_date", start
                )
                ratio = getattr(action, "new_rate", None) or getattr(action, "rate", None)
                amount = getattr(action, "rate", None) if mapped_type == "DIVIDEND" else None
                records.append(
                    CorporateActionRecord(
                        published_at=None,
                        observed_at=now,
                        source=_SOURCE,
                        action_type=mapped_type,
                        ex_date=ex_date,
                        ratio=str(Decimal(str(ratio))) if ratio is not None else None,
                        amount=str(Decimal(str(amount))) if amount is not None else None,
                    )
                )
        return records


class AlpacaStockDataProvider:
    """Implements both `MarketQuoteProvider` and `HistoricalBarsProvider`
    with a single `StockHistoricalDataClient` — one vendor, two
    interfaces, two independent capability/failure surfaces."""

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, MarketQuoteProviderNotConfigured)
        self._client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key_id, secret_key=settings.alpaca_api_secret_key
        )

    def get_capabilities(self) -> MarketQuoteCapabilities:
        return MarketQuoteCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            is_real_time=False,
            supports_extended_hours=False,
        )

    def get_historical_bars_capabilities(self) -> HistoricalBarsCapabilities:
        return HistoricalBarsCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            supports_split_adjustment=True,
            supports_dividend_adjustment=False,
            max_lookback_days=None,
        )

    def get_latest_quote(self, ticker: str) -> QuoteRecord | None:
        request = StockLatestBarRequest(symbol_or_symbols=ticker.upper())
        latest = self._client.get_stock_latest_bar(request)
        bar = latest.get(ticker.upper())
        if bar is None:
            return None
        return QuoteRecord(
            published_at=None,
            observed_at=bar.timestamp,
            source=_SOURCE,
            ticker=ticker.upper(),
            price=str(Decimal(str(bar.close))),
            volume=int(bar.volume),
        )

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[BarRecord]:
        request = StockBarsRequest(
            symbol_or_symbols=ticker.upper(),
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=Adjustment.SPLIT,
        )
        bar_set = self._client.get_stock_bars(request)
        assert isinstance(bar_set, BarSet)
        bars = bar_set.data.get(ticker.upper(), [])
        return [
            BarRecord(
                published_at=None,
                observed_at=bar.timestamp,
                source=_SOURCE,
                ticker=ticker.upper(),
                as_of=bar.timestamp.date(),
                open=str(Decimal(str(bar.open))),
                high=str(Decimal(str(bar.high))),
                low=str(Decimal(str(bar.low))),
                close=str(Decimal(str(bar.close))),
                volume=int(bar.volume),
                adjusted=True,
            )
            for bar in bars
        ]


class AlpacaNewsProvider:
    """`NewsProvider` backed by Alpaca's included news endpoint
    (docs/PROVIDER_MATRIX.md's recommended MVP default — zero new
    vendor, headlines only, no sentiment score)."""

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, NewsProviderNotConfigured)
        self._client = NewsClient(
            api_key=settings.alpaca_api_key_id, secret_key=settings.alpaca_api_secret_key
        )

    def get_capabilities(self) -> NewsCapabilities:
        return NewsCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            supports_full_text=False,
            supports_instrument_tagging=True,
        )

    def get_news(self, ticker: str, since: str) -> list[NewsRecord]:
        request = NewsRequest(symbols=ticker.upper(), start=since, exclude_contentless=True)
        result = self._client.get_news(request)
        assert isinstance(result, NewsSet)
        records: list[NewsRecord] = []
        for item in result.data.get("news", []):
            assert isinstance(item, News)
            dedup_hash = hashlib.sha256(
                f"{item.url}|{item.source}|{item.headline}".encode()
            ).hexdigest()
            records.append(
                NewsRecord(
                    published_at=item.created_at,
                    observed_at=item.created_at,
                    source=_SOURCE,
                    provider_record_id=str(item.id),
                    canonical_url=item.url,
                    publisher=item.source,
                    headline=item.headline,
                    dedup_hash=dedup_hash,
                )
            )
        return records


class AlpacaVolatilityIndexProvider:
    """`VolatilityIndexProvider` backed by VIXY (front-month VIX-futures
    ETN) bars via the existing `StockHistoricalDataClient` —
    docs/PROVIDER_MATRIX.md/BLOCKING_DECISIONS.md #2's recommended
    default: zero new vendor, a documented ETP-proxy approximation, not
    the spot CBOE index tick-for-tick (`is_spot_index=False`, reported
    honestly via capabilities)."""

    _PROXY_TICKER = "VIXY"

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, VolatilityIndexProviderNotConfigured)
        self._client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key_id, secret_key=settings.alpaca_api_secret_key
        )

    def get_capabilities(self) -> VolatilityIndexCapabilities:
        return VolatilityIndexCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            is_spot_index=False,
            supports_term_structure=False,
        )

    def get_level(self, as_of: date) -> VolatilityIndexRecord | None:
        request = StockBarsRequest(
            symbol_or_symbols=self._PROXY_TICKER,
            timeframe=TimeFrame.Day,
            start=as_of,
            end=as_of,
        )
        try:
            bar_set = self._client.get_stock_bars(request)
        except Exception as exc:
            raise VolatilityIndexProviderUnavailable(str(exc)) from exc
        assert isinstance(bar_set, BarSet)
        bars = bar_set.data.get(self._PROXY_TICKER, [])
        if not bars:
            return None
        bar = bars[-1]
        return VolatilityIndexRecord(
            published_at=None,
            observed_at=bar.timestamp,
            source=_SOURCE,
            as_of=bar.timestamp.date(),
            level=str(Decimal(str(bar.close))),
        )


class AlpacaBrokerCapabilityProvider:
    """`BrokerCapabilityProvider` backed by `TradingClient.get_account()`
    — read-only diagnostics, never an order-submission path (see this
    interface's own module docstring)."""

    def __init__(self, settings: Settings) -> None:
        _require_credentials(settings, BrokerCapabilityProviderNotConfigured)
        self._client = TradingClient(
            api_key=settings.alpaca_api_key_id,
            secret_key=settings.alpaca_api_secret_key,
            paper=True,
        )

    def get_capabilities(self) -> BrokerCapabilities:
        account = self._client.get_account()
        assert isinstance(account, TradeAccount)
        return BrokerCapabilities(
            provider_name=_SOURCE,
            is_live_data=True,
            supports_live_trading=False,
            supports_paper_trading=account.status is not None,
            supported_order_types=("MARKET", "LIMIT", "STOP", "STOP_LIMIT"),
            supports_extended_hours=True,
            supports_fractional_shares=True,
            supports_native_brackets=True,
        )


__all__ = [
    "AlpacaBrokerCapabilityProvider",
    "AlpacaCorporateActionsProvider",
    "AlpacaInstrumentReferenceProvider",
    "AlpacaNewsProvider",
    "AlpacaStockDataProvider",
    "AlpacaVolatilityIndexProvider",
]
