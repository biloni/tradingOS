"""AlpacaMarketDataProvider is tested against a mocked alpaca-py client —
no network call, no credentials required, per the project's fixtures-not-
live-APIs test policy."""

from datetime import date
from decimal import Decimal

import pytest
from alpaca.data.models import Bar
from alpaca.data.models.bars import BarSet

from tradingos_api.core.config import Settings
from tradingos_api.providers.alpaca_market_data import AlpacaMarketDataProvider
from tradingos_api.providers.market_data import MarketDataProviderNotConfigured

_RAW_BAR = {
    "t": "2026-07-01T00:00:00Z",
    "o": 100.0,
    "h": 101.5,
    "l": 99.5,
    "c": 100.75,
    "v": 12345,
    "n": 10,
    "vw": 100.5,
}


def _settings_with_keys() -> Settings:
    return Settings(alpaca_api_key_id="test-key", alpaca_api_secret_key="test-secret")


class TestAlpacaMarketDataProviderConfiguration:
    def test_raises_when_keys_missing(self) -> None:
        settings = Settings(alpaca_api_key_id=None, alpaca_api_secret_key=None)
        with pytest.raises(MarketDataProviderNotConfigured):
            AlpacaMarketDataProvider(settings)


class TestGetDailyBars:
    def test_maps_alpaca_bars_to_price_bar_dto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaMarketDataProvider(_settings_with_keys())

        bar_set = BarSet({"AAPL": [_RAW_BAR]})
        monkeypatch.setattr(provider._client, "get_stock_bars", lambda request: bar_set)

        result = provider.get_daily_bars("AAPL", date(2026, 7, 1), date(2026, 7, 1))

        assert len(result) == 1
        dto = result[0]
        assert dto.symbol == "AAPL"
        assert dto.as_of == date(2026, 7, 1)
        assert Decimal(dto.open) == Decimal("100.0")
        assert Decimal(dto.high) == Decimal("101.5")
        assert Decimal(dto.low) == Decimal("99.5")
        assert Decimal(dto.close) == Decimal("100.75")
        assert dto.volume == 12345
        assert dto.source == "alpaca"
        assert dto.timezone == "UTC"

    def test_returns_empty_list_when_symbol_not_in_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = AlpacaMarketDataProvider(_settings_with_keys())
        monkeypatch.setattr(provider._client, "get_stock_bars", lambda request: BarSet({}))
        result = provider.get_daily_bars("AAPL", date(2026, 7, 1), date(2026, 7, 1))
        assert result == []


class TestGetLatestQuote:
    def test_maps_latest_bar_to_price_bar_dto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaMarketDataProvider(_settings_with_keys())
        bar = Bar("AAPL", _RAW_BAR)
        monkeypatch.setattr(provider._client, "get_stock_latest_bar", lambda request: {"AAPL": bar})

        result = provider.get_latest_quote("AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert Decimal(result.close) == Decimal("100.75")

    def test_returns_none_when_no_latest_bar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaMarketDataProvider(_settings_with_keys())
        monkeypatch.setattr(provider._client, "get_stock_latest_bar", lambda request: {})
        assert provider.get_latest_quote("AAPL") is None
