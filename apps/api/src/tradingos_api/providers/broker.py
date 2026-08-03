"""Provider-neutral paper-broker interface.

Alpaca's paper-trading API is the Phase 3 implementation (see
docs/PROVIDER_MATRIX.md, ADR-002). Per project principle 10, live order
placement is intentionally absent from this interface — there is no `place_
live_order` method anywhere in this codebase. A future phase would add a
separate, explicitly-flagged interface for that, gated on human confirmation
per order (principle 11).
"""

from typing import Protocol

from pydantic import BaseModel


class BrokerProviderNotConfigured(RuntimeError):
    """Raised when a PaperBrokerProvider is used without its required
    credentials set — same pattern as MarketDataProviderNotConfigured
    (providers/market_data.py): missing config is shown explicitly, not
    papered over (principle 5)."""


class PaperOrderRequest(BaseModel):
    symbol: str
    quantity: int
    side: str  # "buy" | "sell"
    order_type: str  # "market" | "limit"
    limit_price: str | None = None


class PaperOrderResult(BaseModel):
    broker_order_id: str
    status: str
    filled_quantity: str
    filled_avg_price: str | None
    filled_at: str | None


class PaperBrokerProvider(Protocol):
    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        """Submit an order against the paper-trading account only."""
        ...

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        """Re-fetch a previously-submitted order's current status. Order
        fills are asynchronous — even a market order's `submit_paper_order`
        response commonly reflects a pre-fill state ("new"/"accepted"), with
        the actual fill landing moments later. This is how a caller catches
        up (see routers/paper_orders.py's `confirm`/`refresh` endpoints)."""
        ...

    def get_paper_positions(self) -> list[dict[str, str]]:
        """Return current paper positions as reported by the broker, used to
        reconcile against our own derived PaperPosition snapshot."""
        ...

    def cancel_paper_order(self, broker_order_id: str) -> None:
        """Cancel a previously-submitted paper order at the broker."""
        ...
