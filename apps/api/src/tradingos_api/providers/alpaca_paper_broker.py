from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.models import Order, Position
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

from tradingos_api.core.config import Settings
from tradingos_api.providers.broker import (
    BrokerProviderNotConfigured,
    PaperOrderRequest,
    PaperOrderResult,
)


def _order_to_result(order: Order) -> PaperOrderResult:
    return PaperOrderResult(
        broker_order_id=str(order.id),
        status=order.status.value,
        filled_quantity=str(order.filled_qty) if order.filled_qty is not None else "0",
        filled_avg_price=str(order.filled_avg_price)
        if order.filled_avg_price is not None
        else None,
        filled_at=order.filled_at.isoformat() if order.filled_at is not None else None,
    )


class AlpacaPaperBrokerProvider:
    """Concrete `PaperBrokerProvider` (providers/broker.py) backed by
    `alpaca.trading.client.TradingClient(paper=True)`. There is no
    equivalent live-trading class anywhere in this codebase — see
    providers/broker.py's module docstring (principle 10).
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.alpaca_api_key_id or not settings.alpaca_api_secret_key:
            raise BrokerProviderNotConfigured(
                "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set. "
                "Paper order submission requires an Alpaca account — see README.md."
            )
        self._client = TradingClient(
            api_key=settings.alpaca_api_key_id,
            secret_key=settings.alpaca_api_secret_key,
            paper=True,
        )

    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        side = OrderSide.BUY if request.side.lower() == "buy" else OrderSide.SELL

        order_data: MarketOrderRequest | LimitOrderRequest
        if request.order_type.lower() == "limit":
            if request.limit_price is None:
                raise ValueError("limit_price is required for a LIMIT order")
            order_data = LimitOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(request.limit_price),
            )
        else:
            order_data = MarketOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
            )

        order = self._client.submit_order(order_data=order_data)
        # `raw_data` is never enabled on this client, so the SDK always
        # returns a real Order/Position here — narrow the type for mypy.
        assert isinstance(order, Order)
        return _order_to_result(order)

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        order = self._client.get_order_by_id(broker_order_id)
        assert isinstance(order, Order)
        return _order_to_result(order)

    def get_paper_positions(self) -> list[dict[str, str]]:
        positions = self._client.get_all_positions()
        assert isinstance(positions, list) and all(isinstance(p, Position) for p in positions)
        return [
            {
                "symbol": p.symbol,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "current_price": p.current_price or "",
                "market_value": p.market_value or "",
            }
            for p in positions
        ]

    def cancel_paper_order(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)
