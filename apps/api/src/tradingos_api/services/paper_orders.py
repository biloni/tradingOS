from tradingos_api.models.paper_order import PaperOrderStatus

_FILLED = {"filled"}
_PARTIALLY_FILLED = {"partially_filled"}
_CANCELED = {"canceled", "expired"}
_REJECTED = {"rejected", "suspended"}
# Everything else (new, accepted, pending_new, held, done_for_day, etc.) is
# still "open" from our simplified perspective — SUBMITTED.


def map_alpaca_status(raw_status: str) -> PaperOrderStatus:
    """Map Alpaca's ~17-value order status enum down to our 6-value
    `PaperOrderStatus` (see its docstring for the rationale)."""
    if raw_status in _FILLED:
        return PaperOrderStatus.FILLED
    if raw_status in _PARTIALLY_FILLED:
        return PaperOrderStatus.PARTIALLY_FILLED
    if raw_status in _CANCELED:
        return PaperOrderStatus.CANCELED
    if raw_status in _REJECTED:
        return PaperOrderStatus.REJECTED
    return PaperOrderStatus.SUBMITTED
