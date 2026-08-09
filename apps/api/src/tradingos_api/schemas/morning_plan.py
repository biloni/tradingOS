from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    AlertDeliveryStatus,
    DeliveryChannel,
    MorningPlanSectionKey,
    MorningPlanVersionLabel,
    PlanCompletenessStatus,
)


class MorningPlanQualityCheckResponse(BaseModel):
    check_name: str
    passed: bool
    detail: str | None

    model_config = {"from_attributes": True}


class MorningPlanItemResponse(BaseModel):
    id: uuid.UUID
    recommendation_version_id: uuid.UUID | None
    instrument_id: uuid.UUID | None = None
    display_order: int
    headline: str
    action_label: str | None = None
    # "Every card must expose evidence, deterministic calculations, AI
    # synthesis, policy result, and user/broker state separately" — the
    # five keys below are `card_detail`'s fixed shape
    # (`services/morning_plan_generate.py`); returned as one JSON object
    # rather than five separate response fields purely to avoid
    # duplicating the shape in two places, not because the separation
    # is any less real.
    card_detail: dict[str, Any] = {}

    model_config = {"from_attributes": True}


class TopStatusResponse(BaseModel):
    market_date: date
    is_trading_day: bool
    market_closed_reason: str | None
    countdown_to_open_seconds: int | None
    plan_status: str
    plan_version_id: uuid.UUID | None
    plan_version_label: MorningPlanVersionLabel | None
    generated_at: datetime | None
    evidence_cutoff: datetime | None
    provider_broker_status: str
    regime_classification: str | None
    vix_proxy_level: Decimal | None
    vix_percentile: Decimal | None
    total_equity: Decimal
    cash: Decimal
    exposure_pct: Decimal
    risk_budget_pct: Decimal | None
    operating_mode: str
    kill_switch_active: bool

    model_config = {"from_attributes": True}


class MorningPlanSectionResponse(BaseModel):
    section_key: MorningPlanSectionKey
    display_order: int
    items: list[MorningPlanItemResponse]


class MorningPlanDeliveryEventResponse(BaseModel):
    channel: DeliveryChannel
    status: AlertDeliveryStatus
    delivered_at: datetime | None

    model_config = {"from_attributes": True}


class MorningPlanVersionSummaryResponse(BaseModel):
    id: uuid.UUID
    morning_plan_run_id: uuid.UUID
    plan_date: date
    version_label: MorningPlanVersionLabel
    version_number: int
    evidence_cutoff: datetime
    generated_at: datetime
    completeness_status: PlanCompletenessStatus

    model_config = {"from_attributes": True}


class MorningPlanVersionDetailResponse(MorningPlanVersionSummaryResponse):
    sections: list[MorningPlanSectionResponse]
    quality_checks: list[MorningPlanQualityCheckResponse]
    delivery_events: list[MorningPlanDeliveryEventResponse]


class DashboardResponse(BaseModel):
    """The Morning Decision Dashboard — top status plus the fixed
    section hierarchy. `version` is `None` exactly when `top_status.plan_status`
    is `MARKET_CLOSED`, `INCOMPLETE` (nothing generated yet), or `FAILED`
    — a dashboard with no plan is a legitimate, honestly-labeled state,
    never backfilled with a fabricated one."""

    top_status: TopStatusResponse
    version: MorningPlanVersionDetailResponse | None


class GeneratePlanRequest(BaseModel):
    plan_date: date | None = None  # defaults to today in America/Los_Angeles
    version_label: MorningPlanVersionLabel = MorningPlanVersionLabel.AD_HOC
    triggered_by: str = "manual"
    idempotency_key: str | None = None
