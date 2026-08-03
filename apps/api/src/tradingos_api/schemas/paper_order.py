from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_serializer

from tradingos_api.models.paper_order import PaperOrderSide, PaperOrderStatus, PaperOrderType


class PaperOrderCreate(BaseModel):
    ticker: str
    side: PaperOrderSide
    quantity: int
    order_type: PaperOrderType
    limit_price: Decimal | None = None


class PaperOrderOut(BaseModel):
    id: int
    portfolio_id: int
    ticker: str
    side: PaperOrderSide
    quantity: int
    filled_quantity: int
    order_type: PaperOrderType
    limit_price: Decimal | None
    status: PaperOrderStatus
    broker_order_id: str | None
    filled_avg_price: Decimal | None
    filled_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime

    @field_serializer("limit_price", "filled_avg_price")
    def _serialize_decimal_as_str(self, value: Decimal | None) -> str | None:
        return str(value) if value is not None else None
