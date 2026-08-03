from decimal import Decimal

from pydantic import BaseModel, field_serializer


class PositionOut(BaseModel):
    """Derived, not read from a table — see PaperOrder's docstring / ADR-013.
    Cost basis is a simple weighted average across all BUY fills; this
    doesn't do FIFO/LIFO tax-lot accounting (a known, documented MVP
    simplification, not an oversight — see docs/DECISIONS.md ADR-013)."""

    ticker: str
    quantity: int
    avg_entry_price: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_pl: Decimal | None

    @field_serializer("avg_entry_price", "current_price", "market_value", "unrealized_pl")
    def _serialize_decimal_as_str(self, value: Decimal | None) -> str | None:
        return str(value) if value is not None else None


class PortfolioSnapshotOut(BaseModel):
    cash_usd: Decimal
    positions: list[PositionOut]
    total_market_value: Decimal
    total_equity: Decimal

    @field_serializer("cash_usd", "total_market_value", "total_equity")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)
