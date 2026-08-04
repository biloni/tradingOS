from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import BacktestTradeExitReason


class BacktestTradeResponse(BaseModel):
    instrument_id: uuid.UUID
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    quantity: Decimal
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: BacktestTradeExitReason

    model_config = {"from_attributes": True}


class BacktestRunResponse(BaseModel):
    id: uuid.UUID
    strategy_version_id: uuid.UUID
    date_range_start: date
    date_range_end: date
    parameters: dict[str, Any]
    results_summary: dict[str, Any]
    created_at: datetime
    trades: list[BacktestTradeResponse]
