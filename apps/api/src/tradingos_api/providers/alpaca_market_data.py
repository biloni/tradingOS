from datetime import UTC, date, datetime
from decimal import Decimal

from alpaca.data.enums import Adjustment
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.models import Bar
from alpaca.data.models.bars import BarSet
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame

from tradingos_api.core.config import Settings
from tradingos_api.providers.market_data import MarketDataProviderNotConfigured, PriceBarDTO

# Split-adjusted only, not dividend-adjusted (ADR-010): matches how charting
# platforms display default price series and what momentum/technical
# indicators (SMA/RSI/MACD) expect. Dividend adjustment depresses historical
# closes in a way suited to total-return analysis, not swing-trade signals.
_ADJUSTMENT = Adjustment.SPLIT
_SOURCE = "alpaca"


def _bar_to_dto(symbol: str, bar: Bar) -> PriceBarDTO:
    return PriceBarDTO(
        symbol=symbol,
        as_of=bar.timestamp.date(),
        open=str(Decimal(str(bar.open))),
        high=str(Decimal(str(bar.high))),
        low=str(Decimal(str(bar.low))),
        close=str(Decimal(str(bar.close))),
        volume=int(bar.volume),
        source=_SOURCE,
        fetched_at=datetime.now(UTC).isoformat(),
        timezone="UTC",
    )


class AlpacaMarketDataProvider:
    """Concrete `MarketDataProvider` (see providers/market_data.py) backed by
    Alpaca's `StockHistoricalDataClient` (ADR-009: official SDK, not
    hand-rolled HTTP)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
            raise MarketDataProviderNotConfigured(
                "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set. "
                "Market data ingestion requires an Alpaca account — see README.md."
            )
        self._client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key_id,
            secret_key=settings.alpaca_api_secret_key,
        )

    def get_daily_bars(self, symbol: str, start: date, end: date) -> list[PriceBarDTO]:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=_ADJUSTMENT,
        )
        bar_set = self._client.get_stock_bars(request)
        # `raw_data` is never enabled on this client, so the SDK always
        # returns a BarSet here — narrow the type for mypy.
        assert isinstance(bar_set, BarSet)
        bars = bar_set.data.get(symbol, [])
        return [_bar_to_dto(symbol, bar) for bar in bars]

    def get_latest_quote(self, symbol: str) -> PriceBarDTO | None:
        request = StockLatestBarRequest(symbol_or_symbols=symbol)
        latest = self._client.get_stock_latest_bar(request)
        bar = latest.get(symbol)
        if bar is None:
            return None
        return _bar_to_dto(symbol, bar)
