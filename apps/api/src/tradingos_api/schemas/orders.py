from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from tradingos_api.schemas.instruments import InstrumentResponse


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    quantity: Decimal
    price: Decimal
    executed_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    instrument: InstrumentResponse
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: Decimal
    limit_price: Decimal | None
    status: OrderStatus
    submitted_at: datetime | None
    filled_at: datetime | None
    created_at: datetime
    executions: list[ExecutionResponse]


class OrderCreateRequest(BaseModel):
    account_id: uuid.UUID
    instrument_id: uuid.UUID
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    quantity: Decimal
    limit_price: Decimal | None = None
    idempotency_key: str | None = None


class OrderImportRow(BaseModel):
    """One already-filled historical fill, for backfilling a manual
    journal's history in bulk rather than one propose+confirm round trip
    per past trade."""

    instrument_id: uuid.UUID
    side: OrderSide
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    idempotency_key: str | None = None


class OrderImportRequest(BaseModel):
    account_id: uuid.UUID
    fills: list[OrderImportRow]


class ReconciliationRow(BaseModel):
    account_id: uuid.UUID
    instrument_id: uuid.UUID
    ticker: str
    position_quantity: Decimal
    lots_quantity: Decimal
    discrepancy: Decimal
