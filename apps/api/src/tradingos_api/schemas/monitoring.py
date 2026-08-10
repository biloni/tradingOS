from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.schemas.alerts import AlertResponse
from tradingos_api.schemas.instruments import InstrumentResponse


class ActivePositionCardResponse(BaseModel):
    """One card per open (account, instrument) position — the
    `/positions` monitoring screen (Revision Prompt 11)."""

    instrument: InstrumentResponse
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal | None
    quote_observed_at: datetime | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_pct: Decimal | None
    stop_price: Decimal | None
    target_prices: list[Decimal]
    upcoming_earnings_date: date | None
    lanes: list[str]
    open_alerts: list[AlertResponse]


class TimelineEntryResponse(BaseModel):
    """One row in the event timeline (Revision Prompt 11) — a
    discriminated union collapsed into one shape (`kind` names which
    evidence/alert/workflow table it came from) since the UI renders
    every kind on the same chronological list."""

    occurred_at: datetime
    kind: str
    title: str
    detail: str | None


class PostEarningsWorkflowStatusResponse(BaseModel):
    id: uuid.UUID
    earnings_event_id: uuid.UUID
    instrument_id: uuid.UUID
    account_id: uuid.UUID
    status: str
    reversal_detected: bool
    results_ingested_at: datetime | None
    confirmation_window_ends_at: datetime | None
    pre_event_recommendation_id: uuid.UUID | None
    post_event_recommendation_id: uuid.UUID | None
    detail: str | None

    model_config = {"from_attributes": True}
