from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import RegimeClassification


class RegimeResponse(BaseModel):
    as_of: date
    classification: RegimeClassification
    vix_proxy_level: Decimal | None
    vix_percentile: Decimal | None
    vix_rate_of_change: Decimal | None
    breadth_pct_above_sma50: Decimal | None

    model_config = {"from_attributes": True}


class FreshnessRow(BaseModel):
    instrument_id: uuid.UUID
    ticker: str
    latest_bar_as_of: date | None
    latest_bar_ingested_at: datetime | None
    is_stale: bool


class MarketOverviewResponse(BaseModel):
    regime: RegimeResponse | None
    tracked_instrument_count: int
    stale_instrument_count: int


class BarResponse(BaseModel):
    as_of: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    model_config = {"from_attributes": True}


class IndicatorSnapshotResponse(BaseModel):
    indicator_name: str
    value: Decimal
    as_of: date

    model_config = {"from_attributes": True}
