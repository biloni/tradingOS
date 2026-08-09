"""Provider-neutral paper-broker interface.

Alpaca's paper-trading API is the Phase 3 implementation (see
docs/PROVIDER_MATRIX.md, ADR-002). Per project principle 10, live order
placement is intentionally absent from this interface — there is no `place_
live_order` method anywhere in this codebase. A future phase would add a
separate, explicitly-flagged interface for that, gated on human confirmation
per order (principle 11).

Revision Prompt 10 additive fields/methods (the actual paper-submission
path, wired up in `services/order_execution.py` — this Protocol's single
caller): `client_order_id` is the broker-facing idempotency key that
stays **stable across retries of the same approval** (never regenerated
per attempt) — this is what lets `find_order_by_client_id()` answer "did
this already go through" after an ambiguous timeout, without ever
resubmitting an order whose outcome is genuinely unknown.
`take_profit_price`/`stop_loss_price` (both optional; a request with
either set is a bracket request) let a conforming implementation submit
a **broker-native** bracket in one call when it supports one
(`BrokerCapabilities.supports_native_brackets`) — see
`services/bracket_execution.py` for the native-vs-emulated decision and
the required reliability disclosure when only emulation is available.
"""

from typing import Protocol

from pydantic import BaseModel


class BrokerProviderNotConfigured(RuntimeError):
    """Raised when a PaperBrokerProvider is used without its required
    credentials set — same pattern as MarketDataProviderNotConfigured
    (providers/market_data.py): missing config is shown explicitly, not
    papered over (principle 5)."""


class BrokerSubmissionAmbiguous(RuntimeError):
    """A conforming `PaperBrokerProvider.submit_paper_order()` implementation
    raises this — never any other exception type — specifically when a
    network timeout or connection failure means it is genuinely unknown
    whether the broker received and accepted the request. This is the
    one signal `services/order_execution.py` treats as "query status
    before any retry" (Revision Prompt 10) rather than either assuming
    success (risking a phantom fill) or assuming failure (risking a
    duplicate resubmit). Any other exception from `submit_paper_order()`
    is treated as a confirmed non-submission, safe to retry directly."""


class PaperOrderRequest(BaseModel):
    symbol: str
    quantity: int
    side: str  # "buy" | "sell"
    order_type: str  # "market" | "limit" | "stop" | "stop_limit"
    limit_price: str | None = None
    stop_price: str | None = None
    client_order_id: str | None = None
    take_profit_price: str | None = None
    stop_loss_price: str | None = None


class PaperOrderResult(BaseModel):
    broker_order_id: str
    status: str
    filled_quantity: str
    filled_avg_price: str | None
    filled_at: str | None
    client_order_id: str | None = None


class PaperBrokerProvider(Protocol):
    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        """Submit an order against the paper-trading account only."""
        ...

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        """Re-fetch a previously-submitted order's current status. Order
        fills are asynchronous — even a market order's `submit_paper_order`
        response commonly reflects a pre-fill state ("new"/"accepted"), with
        the actual fill landing moments later. This is how a caller catches
        up (`services/order_execution.py::poll_and_reconcile_fills()`)."""
        ...

    def find_order_by_client_id(self, client_order_id: str) -> PaperOrderResult | None:
        """`None` if no order with this `client_order_id` was ever
        accepted by the broker — the "query status before any retry"
        step (Revision Prompt 10) a submit call's caller runs after an
        ambiguous timeout, before ever considering a second submit."""
        ...

    def get_paper_positions(self) -> list[dict[str, str]]:
        """Return current paper positions as reported by the broker, used to
        reconcile against our own derived PaperPosition snapshot."""
        ...

    def cancel_paper_order(self, broker_order_id: str) -> None:
        """Cancel a previously-submitted paper order at the broker."""
        ...
