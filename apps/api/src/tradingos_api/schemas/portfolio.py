from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import AccountType
from tradingos_api.schemas.instruments import InstrumentResponse


class AccountResponse(BaseModel):
    id: uuid.UUID
    account_type: AccountType
    name: str
    base_currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    instrument: InstrumentResponse
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal | None


class CashSummaryResponse(BaseModel):
    account_id: uuid.UUID
    cash: Decimal
    starting_cash: Decimal


class RiskSnapshotResponse(BaseModel):
    as_of: datetime
    gross_exposure_pct: Decimal | None
    largest_position_pct: Decimal | None
    sector_concentration: dict[str, Any] | None
    correlation_flag: bool

    model_config = {"from_attributes": True}


class AccountDetailResponse(BaseModel):
    account: AccountResponse
    cash: CashSummaryResponse
    positions: list[PositionResponse]
    latest_risk_snapshot: RiskSnapshotResponse | None
