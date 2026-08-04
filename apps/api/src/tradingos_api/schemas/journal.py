from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import TradeReviewRating, TradeStatus
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


class TradeNoteCreateRequest(BaseModel):
    note_text: str


class TradeReviewCreateRequest(BaseModel):
    rating: TradeReviewRating | None = None
    review_text: str | None = None
