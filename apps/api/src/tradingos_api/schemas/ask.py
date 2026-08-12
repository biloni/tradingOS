"""Request/response shapes for `POST /api/v1/ask` (Revision Prompt 4's
ADR-019, rebuilt against the current schema during end-to-end platform
testing after the original MVP router was deleted in the Phase 8
domain-model migration). `RecommendationSummary` is what the tool-use
loop hands back once `get_recommendations`/`get_upcoming_earnings`
surfaces a real `Recommendation` row — a pointer plus the fields the
chat UI renders, never a number the model invented itself."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from tradingos_api.models.enums import RecommendationConfidence


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RecommendationSummary(BaseModel):
    recommendation_id: uuid.UUID
    ticker: str
    mode: str
    lane_action: str | None
    confidence: RecommendationConfidence
    score: Decimal | None


class AskResponse(BaseModel):
    answer: str
    recommendations: list[RecommendationSummary]
    model_call_record_ids: list[uuid.UUID]
    iterations: int
