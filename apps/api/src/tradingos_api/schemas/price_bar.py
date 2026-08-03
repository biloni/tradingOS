from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class PriceBarOut(BaseModel):
    """Money fields are `Decimal` internally (never float-math currency) but
    serialize to JSON as strings, matching `PriceBarDTO`'s convention in
    providers/market_data.py — avoids float-precision surprises on the wire.
    """

    model_config = ConfigDict(from_attributes=True)

    as_of: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str
    adjustment: str
    fetched_at: datetime

    @field_serializer("open", "high", "low", "close")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)
