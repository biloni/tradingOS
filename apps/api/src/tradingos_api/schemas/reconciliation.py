from decimal import Decimal

from pydantic import BaseModel, field_serializer


class ReconciliationRowOut(BaseModel):
    """Compares our derived positions (services/portfolio.py) against what
    Alpaca's own paper account reports (Phase 3's explicit reconciliation
    deliverable). A nonzero `discrepancy` means our fill records and
    Alpaca's book have diverged and warrants investigation."""

    ticker: str
    our_quantity: int
    alpaca_quantity: Decimal
    discrepancy: Decimal

    @field_serializer("alpaca_quantity", "discrepancy")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)
