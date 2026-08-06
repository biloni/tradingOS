from __future__ import annotations

import uuid
from datetime import date, datetime

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
    display_order: int
    headline: str

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


class MorningPlanRerunRequest(BaseModel):
    plan_date: date
    version_label: MorningPlanVersionLabel = MorningPlanVersionLabel.AD_HOC
    triggered_by: str = "manual"
    idempotency_key: str | None = None
