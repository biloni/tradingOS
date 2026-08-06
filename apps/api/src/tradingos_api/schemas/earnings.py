from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import EarningsTimingCategory, RecommendationConfidence
from tradingos_api.schemas.instruments import InstrumentResponse


class EarningsEventCalendarRowResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    report_date: date
    timing_category: EarningsTimingCategory
    verified_date: date | None
    confidence: RecommendationConfidence | None

    model_config = {"from_attributes": True}


class EarningsConsensusSnapshotResponse(BaseModel):
    as_of: date
    consensus_eps: Decimal | None
    consensus_revenue: Decimal | None
    num_analysts: int | None
    source: str
    observed_at: datetime

    model_config = {"from_attributes": True}


class EarningsGuidanceItemResponse(BaseModel):
    metric: str
    guidance_low: Decimal | None
    guidance_high: Decimal | None
    period: str | None
    issued_at: datetime
    source: str

    model_config = {"from_attributes": True}


class EarningsActualResponse(BaseModel):
    metric: str
    actual_value: Decimal
    reported_at: datetime
    usable_at: datetime
    source: str

    model_config = {"from_attributes": True}


class EventExpectedMoveSnapshotResponse(BaseModel):
    as_of: datetime
    evidence_cutoff: datetime
    atr_based_move_pct: Decimal | None
    historical_gap_move_pct: Decimal | None
    option_implied_move_pct: Decimal | None
    selected_expected_move_pct: Decimal
    calculation_version: str

    model_config = {"from_attributes": True}


class EarningsFeatureSnapshotResponse(BaseModel):
    as_of: datetime
    evidence_cutoff: datetime
    is_pre_event: bool
    component_price_trend: Decimal | None
    component_analyst_revisions: Decimal | None
    component_options_skew: Decimal | None
    component_peer_reactions: Decimal | None
    component_historical_drift: Decimal | None
    component_guidance_momentum: Decimal | None
    component_technical_setup: Decimal | None
    component_sentiment: Decimal | None
    total_score: Decimal
    calculation_version: str

    model_config = {"from_attributes": True}


class PostEarningsConfirmationSnapshotResponse(BaseModel):
    as_of: datetime
    evidence_cutoff: datetime
    results_gate_passed: bool
    guidance_gate_passed: bool
    market_reaction_gate_passed: bool
    all_gates_passed: bool
    notes: str | None

    model_config = {"from_attributes": True}


class EarningsEventDetailResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    fiscal_period: str | None
    report_date: date
    verified_date: date | None
    exchange_local_date: date | None
    timing_category: EarningsTimingCategory
    verification_source: str | None
    expected_report_period: str | None
    confidence: RecommendationConfidence | None
    eps_estimate: Decimal | None
    eps_actual: Decimal | None
    consensus_snapshots: list[EarningsConsensusSnapshotResponse]
    guidance_items: list[EarningsGuidanceItemResponse]
    actuals: list[EarningsActualResponse]
    latest_expected_move: EventExpectedMoveSnapshotResponse | None
    latest_feature_snapshot: EarningsFeatureSnapshotResponse | None
