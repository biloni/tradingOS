from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from tradingos_api.models.enums import RecommendationStatus, ThesisStatus
from tradingos_api.schemas.instruments import InstrumentResponse


class ThesisCatalystResponse(BaseModel):
    catalyst_text: str
    expected_date: date | None

    model_config = {"from_attributes": True}


class ThesisRiskResponse(BaseModel):
    risk_text: str

    model_config = {"from_attributes": True}


class ThesisStatusHistoryResponse(BaseModel):
    from_status: ThesisStatus | None
    to_status: ThesisStatus
    reason: str | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class ValuationSnapshotResponse(BaseModel):
    as_of: date
    method: str
    fair_value_low: Decimal | None
    fair_value_mid: Decimal | None
    fair_value_high: Decimal | None
    source: str
    observed_at: datetime

    model_config = {"from_attributes": True}


class InvestmentThesisVersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    valuation_low: Decimal | None
    valuation_mid: Decimal | None
    valuation_high: Decimal | None
    thesis_text: str
    horizon_days_min: int | None
    horizon_days_max: int | None
    review_date: date | None
    generated_at: datetime
    catalysts: list[ThesisCatalystResponse]
    risks: list[ThesisRiskResponse]


class InvestmentThesisDetailResponse(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    instrument: InstrumentResponse
    status: ThesisStatus
    latest_version: InvestmentThesisVersionResponse | None
    valuation_snapshots: list[ValuationSnapshotResponse]
    status_history: list[ThesisStatusHistoryResponse]
    # Revision Prompt 7 — the remaining "INVESTMENT ACTION PLAN" fields
    # that don't have their own table, read from the parent
    # `Recommendation`'s latest `RecommendationVersion` (thesis-break
    # conditions have their own child table; the rest live in
    # `deterministic_inputs_snapshot`, see
    # `services/committee_orchestrator.py::_deterministic_inputs_snapshot()`).
    thesis_break_conditions: list[str] = []
    lane_action: str | None = None
    preferred_accumulation_zone: str | None = None
    tranche_plan: str | None = None
    proposed_max_allocation_pct: str | None = None
    portfolio_role: str | None = None
    why_investment_not_trade: str | None = None


class InvestmentRecommendationSummaryResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    status: RecommendationStatus
    opened_at: datetime
    thesis_id: uuid.UUID | None
