from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from tradingos_api.models.enums import MonitoringFrequency
from tradingos_api.schemas.instruments import InstrumentResponse


class WatchlistResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WatchlistItemResponse(BaseModel):
    id: uuid.UUID
    watchlist_id: uuid.UUID
    instrument: InstrumentResponse
    tier: int
    priority: int
    active: bool
    notes: str | None
    monitoring_frequency: MonitoringFrequency
    added_at: date
    updated_at: datetime


class WatchlistItemCreateRequest(BaseModel):
    instrument_id: uuid.UUID
    tier: int = 1
    priority: int = 0
    notes: str | None = None
    monitoring_frequency: MonitoringFrequency = MonitoringFrequency.DAILY


class WatchlistItemUpdateRequest(BaseModel):
    """`expected_updated_at` implements optimistic concurrency: a stale
    write (the item changed since the client last read it) is rejected
    with 409 rather than silently overwriting a concurrent change."""

    expected_updated_at: datetime
    tier: int | None = None
    priority: int | None = None
    active: bool | None = None
    notes: str | None = None
    monitoring_frequency: MonitoringFrequency | None = None
