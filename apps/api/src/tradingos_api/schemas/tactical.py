from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import RecommendationConfidence, RecommendationStatus
from tradingos_api.schemas.instruments import InstrumentResponse


class TacticalRecommendationVersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    lane_action: str | None
    confidence: RecommendationConfidence
    score: Decimal | None
    rationale: str
    horizon_days_min: int | None
    horizon_days_max: int | None
    review_date: date | None
    generated_at: datetime


class TacticalRecommendationSummaryResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    status: RecommendationStatus
    opened_at: datetime
    latest_version: TacticalRecommendationVersionResponse | None
