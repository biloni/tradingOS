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


class PaperOrderRequest(BaseModel):
    symbol: str
    quantity: int
    side: str  # "buy" | "sell"
    order_type: str  # "market" | "limit"
    limit_price: str | None = None


class PaperOrderResult(BaseModel):
    broker_order_id: str
    status: str
    filled_avg_price: str | None
    filled_at: str | None


class PaperBrokerProvider(Protocol):
    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        """Submit an order against the paper-trading account only."""
        ...

    def get_paper_positions(self) -> list[dict[str, str]]:
        """Return current paper positions as reported by the broker, used to
        reconcile against our own derived PaperPosition snapshot."""
        ...
