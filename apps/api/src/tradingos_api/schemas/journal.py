from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import JournalExitReason, LotLane, TradeReviewRating, TradeStatus
from tradingos_api.schemas.instruments import InstrumentResponse


class TradeNoteResponse(BaseModel):
    id: uuid.UUID
    note_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeReviewResponse(BaseModel):
    rating: TradeReviewRating | None
    review_text: str | None
    reviewed_at: datetime

    model_config = {"from_attributes": True}


class TradeThesisResponse(BaseModel):
    thesis_text: str
    catalyst_text: str | None
    original_stop_price: Decimal | None
    is_intact: bool

    model_config = {"from_attributes": True}


class TradeDetailResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    instrument: InstrumentResponse
    status: TradeStatus
    opened_at: datetime
    closed_at: datetime | None
    quantity: Decimal
    realized_pnl: Decimal | None
    thesis: TradeThesisResponse | None
    notes: list[TradeNoteResponse]
    reviews: list[TradeReviewResponse]
    # Revision Prompt 8 — "capture recommendation, lane, user response,
    # approval, order, fill, modifications, reason, outcome, maximum
    # favorable/adverse excursion, exit reason, benchmark result, and
    # post-trade lesson." See `services/trade_journal.py::JournalEntryView`
    # — this is that same composed read model, flattened onto the
    # existing trade-detail response rather than a second endpoint.
    lane: LotLane
    outcome: str
    exit_reason: JournalExitReason | None
    mfe: Decimal | None
    mae: Decimal | None
    modifications_text: str | None
    recommendation_outcome: str | None
    order_approval_status: str | None
    benchmark_ticker: str | None
    benchmark_return_pct: Decimal | None
    post_trade_lesson: str | None


class TradeNoteCreateRequest(BaseModel):
    note_text: str


class TradeReviewCreateRequest(BaseModel):
    rating: TradeReviewRating | None = None
    review_text: str | None = None
