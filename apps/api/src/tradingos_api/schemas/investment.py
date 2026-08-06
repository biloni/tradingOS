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


class InvestmentRecommendationSummaryResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    status: RecommendationStatus
    opened_at: datetime
    thesis_id: uuid.UUID | None
