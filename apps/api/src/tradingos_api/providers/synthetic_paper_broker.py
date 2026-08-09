"""Deterministic, in-memory paper-broker implementation (Revision
Prompt 10) — lets the full order-execution flow (propose -> approve ->
submit -> fill -> reconcile) run and be demoed without a configured
Alpaca account, matching this project's established "graceful, honest
degradation without a paid vendor" pattern (Revision Prompt 4's
synthetic evidence providers). Never used for anything but `PAPER`
submissions — see `providers/broker.py`'s module docstring; there is no
live-capable variant of this class or any other in this codebase.

Fill behavior is intentionally simple and fully deterministic (no RNG,
no wall-clock dependency beyond the timestamp on the fill itself): a
MARKET order fills immediately at this instance's configured
`reference_prices` (standing in for "the fresh quote refreshed
immediately before submission" — this provider has no market-data
opinion of its own, the caller's own quote provider does). A LIMIT
order stays `new` until `simulate_fill()`/`simulate_partial_fill()` is
called explicitly, modeling a resting order a real broker fills
asynchronously, at its own pace, once the market actually trades
through the limit price — exactly the "order fills are asynchronous"
property `providers/broker.py`'s own docstring describes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from tradingos_api.providers.broker import PaperOrderRequest, PaperOrderResult
from tradingos_api.providers.broker_capability import BrokerCapabilities

_DEFAULT_REFERENCE_PRICE = Decimal("100.00")
_SOURCE = "synthetic_fixture"


class SyntheticBrokerCapabilityProvider:
    """The `BrokerCapabilityProvider` sibling for
    `SyntheticPaperBrokerProvider` — `supports_native_brackets=False`
    deliberately (unlike the real Alpaca capability provider), so the
    emulated-bracket-with-disclosure path
    (`services/bracket_execution.py`) has a real, exercisable provider
    to demo and test against, not just Alpaca's native-supporting one."""

    def get_capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            provider_name=_SOURCE,
            is_live_data=False,
            supports_live_trading=False,
            supports_paper_trading=True,
            supported_order_types=("MARKET", "LIMIT"),
            supports_extended_hours=False,
            supports_fractional_shares=False,
            supports_native_brackets=False,
        )


@dataclass
class _SyntheticOrder:
    broker_order_id: str
    client_order_id: str | None
    symbol: str
    quantity: Decimal
    side: str
    order_type: str
    limit_price: Decimal | None
    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    status: str  # "new" | "filled" | "partially_filled" | "canceled" | "rejected"
    filled_quantity: Decimal = field(default_factory=lambda: Decimal(0))
    filled_avg_price: Decimal | None = None
    filled_at: datetime | None = None


class SyntheticBrokerOrderNotFound(RuntimeError):
    pass


class SyntheticPaperBrokerProvider:
    """A `PaperBrokerProvider` (`providers/broker.py`) with fully
    inspectable, controllable in-memory state — the same role
    `SyntheticFundamentalsProvider` etc. play for Revision Prompt 4's
    evidence layer, now for order execution."""

    def __init__(
        self,
        *,
        reference_prices: dict[str, Decimal] | None = None,
        reject_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._orders: dict[str, _SyntheticOrder] = {}
        self._by_client_id: dict[str, str] = {}
        self._reference_prices = reference_prices or {}
        self._reject_symbols = reject_symbols

    def _to_result(self, order: _SyntheticOrder) -> PaperOrderResult:
        return PaperOrderResult(
            broker_order_id=order.broker_order_id,
            status=order.status,
            filled_quantity=str(order.filled_quantity),
            filled_avg_price=str(order.filled_avg_price)
            if order.filled_avg_price is not None
            else None,
            filled_at=order.filled_at.isoformat() if order.filled_at is not None else None,
            client_order_id=order.client_order_id,
        )

    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        # Broker-side idempotency: a resubmit with the same
        # `client_order_id` returns the existing order rather than
        # creating a second one — `find_order_by_client_id()` is the
        # safety net a caller should check *before* ever relying on
        # this, but a real broker would behave this way regardless.
        if request.client_order_id and request.client_order_id in self._by_client_id:
            existing = self._orders[self._by_client_id[request.client_order_id]]
            return self._to_result(existing)

        symbol = request.symbol.upper()
        order_id = str(uuid.uuid4())
        limit_price = Decimal(request.limit_price) if request.limit_price is not None else None
        take_profit = (
            Decimal(request.take_profit_price) if request.take_profit_price is not None else None
        )
        stop_loss = (
            Decimal(request.stop_loss_price) if request.stop_loss_price is not None else None
        )

        if symbol in self._reject_symbols:
            order = _SyntheticOrder(
                broker_order_id=order_id,
                client_order_id=request.client_order_id,
                symbol=symbol,
                quantity=Decimal(request.quantity),
                side=request.side,
                order_type=request.order_type,
                limit_price=limit_price,
                take_profit_price=take_profit,
                stop_loss_price=stop_loss,
                status="rejected",
            )
            self._orders[order_id] = order
            if request.client_order_id:
                self._by_client_id[request.client_order_id] = order_id
            return self._to_result(order)

        order = _SyntheticOrder(
            broker_order_id=order_id,
            client_order_id=request.client_order_id,
            symbol=symbol,
            quantity=Decimal(request.quantity),
            side=request.side,
            order_type=request.order_type,
            limit_price=limit_price,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
            status="new",
        )
        self._orders[order_id] = order
        if request.client_order_id:
            self._by_client_id[request.client_order_id] = order_id

        if request.order_type.lower() == "market":
            fill_price = self._reference_prices.get(symbol, _DEFAULT_REFERENCE_PRICE)
            self.simulate_fill(order_id, order.quantity, fill_price)
            order = self._orders[order_id]

        return self._to_result(order)

    def simulate_partial_fill(
        self, broker_order_id: str, quantity: Decimal, price: Decimal
    ) -> PaperOrderResult:
        """Test/demo control surface — books `quantity` more shares at
        `price` against an already-accepted order, leaving it
        `partially_filled` if quantity remains open or `filled` once it
        doesn't. Never used by `services/order_execution.py` itself,
        which only ever reads fill state via `get_paper_order_status()`/
        `find_order_by_client_id()`, the same way it would have to
        against a real broker."""
        order = self._orders.get(broker_order_id)
        if order is None:
            raise SyntheticBrokerOrderNotFound(broker_order_id)
        new_filled = order.filled_quantity + quantity
        if new_filled > order.quantity:
            raise ValueError(
                f"cannot fill {quantity} more — only "
                f"{order.quantity - order.filled_quantity} remains open"
            )
        total_cost = (order.filled_avg_price or Decimal(0)) * order.filled_quantity + (
            price * quantity
        )
        order.filled_quantity = new_filled
        order.filled_avg_price = (total_cost / new_filled) if new_filled > 0 else None
        order.filled_at = datetime.now(UTC)
        order.status = "filled" if new_filled == order.quantity else "partially_filled"
        return self._to_result(order)

    def simulate_fill(
        self, broker_order_id: str, quantity: Decimal, price: Decimal
    ) -> PaperOrderResult:
        return self.simulate_partial_fill(broker_order_id, quantity, price)

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        order = self._orders.get(broker_order_id)
        if order is None:
            raise SyntheticBrokerOrderNotFound(broker_order_id)
        return self._to_result(order)

    def find_order_by_client_id(self, client_order_id: str) -> PaperOrderResult | None:
        order_id = self._by_client_id.get(client_order_id)
        if order_id is None:
            return None
        return self._to_result(self._orders[order_id])

    def get_paper_positions(self) -> list[dict[str, str]]:
        totals: dict[str, Decimal] = {}
        for order in self._orders.values():
            if order.filled_quantity <= 0:
                continue
            signed = (
                order.filled_quantity if order.side.lower() == "buy" else -order.filled_quantity
            )
            totals[order.symbol] = totals.get(order.symbol, Decimal(0)) + signed
        return [
            {
                "symbol": symbol,
                "qty": str(qty),
                "avg_entry_price": "",
                "current_price": "",
                "market_value": "",
            }
            for symbol, qty in totals.items()
            if qty != 0
        ]

    def cancel_paper_order(self, broker_order_id: str) -> None:
        order = self._orders.get(broker_order_id)
        if order is None:
            raise SyntheticBrokerOrderNotFound(broker_order_id)
        order.status = "canceled"
