from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItemRequest(BaseModel):
    evidence_id: str
    evidence_type: str
    summary: str


class CommitteeRunRequest(BaseModel):
    """A human-assembled evidence bundle + deterministic inputs — this
    endpoint runs the committee synchronously against exactly what's
    submitted here; it never fetches evidence on its own (Revision
    Prompt 6: "do not schedule production runs" — every run is a
    reviewed, explicit submission, matching the "review screens"
    requirement)."""

    symbol: str
    evidence_cutoff: datetime
    evidence: list[EvidenceItemRequest] = Field(default_factory=list)
    deterministic_feature_ids: list[str] = Field(default_factory=list)
    deterministic_summary: str
    hard_veto_active: bool
    hard_veto_reason: str | None = None
    watchlist_item_id: uuid.UUID | None = None
    cost_ceiling_usd: Decimal = Decimal("1.00")
    per_call_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    triggered_by: str = "MANUAL"


class RoleRunResponse(BaseModel):
    role: str
    display_name: str
    status: Literal["SUCCEEDED", "FAILED", "DEGRADED"]
    error_detail: str | None
    output: dict[str, Any] | None
    model: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: Decimal


class CommitteeRunResponse(BaseModel):
    session_id: uuid.UUID
    lane: Literal["INVESTMENT", "TACTICAL"]
    status: str
    role_runs: list[RoleRunResponse]
    total_cost_usd: Decimal
    recommendation_id: uuid.UUID | None
    lane_action: str | None
    veto_override_applied: bool


class LaneConclusionResponse(BaseModel):
    recommendation_id: uuid.UUID
    lane_action: str | None
    confidence: str
    rationale: str
    horizon_days_min: int | None
    horizon_days_max: int | None
    review_date: str | None
    generated_at: str


class SideBySideResponse(BaseModel):
    instrument_id: uuid.UUID
    investment: LaneConclusionResponse | None
    tactical: LaneConclusionResponse | None
    divergence_explanation: str
