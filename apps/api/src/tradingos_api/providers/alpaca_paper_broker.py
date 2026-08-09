from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.models import Order, Position
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
)

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
        client_order_id=order.client_order_id,
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
        is_bracket = request.take_profit_price is not None or request.stop_loss_price is not None
        bracket_kwargs: dict[str, object] = {}
        if is_bracket:
            bracket_kwargs["order_class"] = OrderClass.BRACKET
            if request.take_profit_price is not None:
                bracket_kwargs["take_profit"] = TakeProfitRequest(
                    limit_price=float(request.take_profit_price)
                )
            if request.stop_loss_price is not None:
                bracket_kwargs["stop_loss"] = StopLossRequest(
                    stop_price=float(request.stop_loss_price)
                )

        order_type = request.order_type.lower()
        order_data: (
            MarketOrderRequest | LimitOrderRequest | StopOrderRequest | StopLimitOrderRequest
        )
        if order_type == "limit":
            if request.limit_price is None:
                raise ValueError("limit_price is required for a LIMIT order")
            order_data = LimitOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(request.limit_price),
                client_order_id=request.client_order_id,
                **bracket_kwargs,
            )
        elif order_type == "stop":
            if request.stop_price is None:
                raise ValueError("stop_price is required for a STOP order")
            order_data = StopOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
                stop_price=float(request.stop_price),
                client_order_id=request.client_order_id,
                **bracket_kwargs,
            )
        elif order_type == "stop_limit":
            if request.stop_price is None or request.limit_price is None:
                raise ValueError(
                    "stop_price and limit_price are both required for a STOP_LIMIT order"
                )
            order_data = StopLimitOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
                stop_price=float(request.stop_price),
                limit_price=float(request.limit_price),
                client_order_id=request.client_order_id,
                **bracket_kwargs,
            )
        else:
            order_data = MarketOrderRequest(
                symbol=request.symbol,
                qty=request.quantity,
                side=side,
                time_in_force=TimeInForce.DAY,
                client_order_id=request.client_order_id,
                **bracket_kwargs,
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

    def find_order_by_client_id(self, client_order_id: str) -> PaperOrderResult | None:
        """`get_order_by_client_id()` raises `APIError` (HTTP 404) when
        no order was ever accepted under this `client_order_id` — that
        is the honest, expected "not found" case here, not a real
        failure, so it maps to `None` rather than propagating."""
        try:
            order = self._client.get_order_by_client_id(client_order_id)
        except APIError:
            return None
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
