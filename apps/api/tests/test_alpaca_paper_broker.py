"""AlpacaPaperBrokerProvider is tested against a mocked alpaca-py
TradingClient — no network call, no real (even paper) order placed, per the
project's fixtures-not-live-APIs test policy."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alpaca.trading.enums import (
    AssetClass,
    AssetExchange,
    OrderClass,
    OrderStatus,
    OrderType,
    PositionSide,
)
from alpaca.trading.models import Order, Position

from tradingos_api.core.config import Settings
from tradingos_api.providers.alpaca_paper_broker import AlpacaPaperBrokerProvider
from tradingos_api.providers.broker import BrokerProviderNotConfigured, PaperOrderRequest


def _settings_with_keys() -> Settings:
    return Settings(alpaca_api_key_id="test-key", alpaca_api_secret_key="test-secret")


def _fake_order(**overrides: object) -> Order:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(),
        client_order_id="test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        submitted_at=datetime.now(UTC),
        symbol="SPY",
        qty="1",
        filled_qty="1",
        filled_avg_price="500.00",
        order_class=OrderClass.SIMPLE,
        order_type=OrderType.MARKET,
        type=OrderType.MARKET,
        side="buy",
        time_in_force="day",
        status=OrderStatus.FILLED,
        extended_hours=False,
        filled_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Order(**defaults)


class TestConfiguration:
    def test_raises_when_keys_missing(self) -> None:
        settings = Settings(alpaca_api_key_id=None, alpaca_api_secret_key=None)
        with pytest.raises(BrokerProviderNotConfigured):
            AlpacaPaperBrokerProvider(settings)


class TestSubmitPaperOrder:
    def test_maps_filled_market_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaPaperBrokerProvider(_settings_with_keys())
        order = _fake_order()
        monkeypatch.setattr(provider._client, "submit_order", lambda order_data: order)

        result = provider.submit_paper_order(
            PaperOrderRequest(symbol="SPY", quantity=1, side="buy", order_type="market")
        )

        assert result.broker_order_id == str(order.id)
        assert result.status == "filled"
        assert result.filled_quantity == "1"
        assert Decimal(result.filled_avg_price or "0") == Decimal("500.00")
        assert result.filled_at is not None

    def test_maps_open_limit_order_with_no_fill_yet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaPaperBrokerProvider(_settings_with_keys())
        order = _fake_order(
            status=OrderStatus.NEW,
            filled_qty="0",
            filled_avg_price=None,
            filled_at=None,
        )
        monkeypatch.setattr(provider._client, "submit_order", lambda order_data: order)

        result = provider.submit_paper_order(
            PaperOrderRequest(
                symbol="SPY", quantity=1, side="buy", order_type="limit", limit_price="490.00"
            )
        )

        assert result.status == "new"
        assert result.filled_quantity == "0"
        assert result.filled_avg_price is None
        assert result.filled_at is None

    def test_limit_order_without_price_raises(self) -> None:
        provider = AlpacaPaperBrokerProvider(_settings_with_keys())
        with pytest.raises(ValueError, match="limit_price"):
            provider.submit_paper_order(
                PaperOrderRequest(symbol="SPY", quantity=1, side="buy", order_type="limit")
            )


class TestGetPaperPositions:
    def test_maps_positions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaPaperBrokerProvider(_settings_with_keys())
        position = Position(
            asset_id=uuid.uuid4(),
            symbol="SPY",
            exchange=AssetExchange.NYSE,
            asset_class=AssetClass.US_EQUITY,
            avg_entry_price="500.00",
            qty="2",
            side=PositionSide.LONG,
            cost_basis="1000.00",
            current_price="510.00",
            market_value="1020.00",
        )
        monkeypatch.setattr(provider._client, "get_all_positions", lambda: [position])

        result = provider.get_paper_positions()

        assert result == [
            {
                "symbol": "SPY",
                "qty": "2",
                "avg_entry_price": "500.00",
                "current_price": "510.00",
                "market_value": "1020.00",
            }
        ]


class TestCancelPaperOrder:
    def test_delegates_to_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AlpacaPaperBrokerProvider(_settings_with_keys())
        calls: list[str] = []
        monkeypatch.setattr(provider._client, "cancel_order_by_id", calls.append)

        provider.cancel_paper_order("abc-123")

        assert calls == ["abc-123"]
