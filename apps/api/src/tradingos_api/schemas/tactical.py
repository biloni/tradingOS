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
    # Revision Prompt 7 — the "TACTICAL PRE-EARNINGS PLAN"/"TACTICAL
    # POST-CONFIRMATION PLAN" fields that don't have their own column:
    # `entry_invalidation` (this recommendation's own invalidation
    # condition) and the rest of the CIO's stated setup, read from
    # `deterministic_inputs_snapshot`
    # (`services/committee_orchestrator.py::_deterministic_inputs_snapshot()`).
    entry_invalidation: str | None = None
    setup_and_event_phase: str | None = None
    key_catalyst: str | None = None
    gap_risk: str | None = None
    liquidity_risk: str | None = None
    order_proposal_id: uuid.UUID | None = None
    order_proposal_status: str | None = None


class TacticalRecommendationSummaryResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    status: RecommendationStatus
    opened_at: datetime
    latest_version: TacticalRecommendationVersionResponse | None
