from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    AgentRole,
    AgentRunStatus,
    CommitteeSessionStatus,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationLevelKind,
    RecommendationStatus,
)
from tradingos_api.schemas.instruments import InstrumentResponse


class RecommendationLevelResponse(BaseModel):
    kind: RecommendationLevelKind
    price: Decimal
    basis: str | None

    model_config = {"from_attributes": True}


class RecommendationVersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    action: RecommendationAction
    confidence: RecommendationConfidence
    score: Decimal | None
    rationale: str
    generated_at: datetime
    levels: list[RecommendationLevelResponse]
    committee_session_id: uuid.UUID | None = None
    """Revision Prompt 15 — the one-click path from a recommendation to
    its committee's per-role opinions (`GET .../committee-sessions/{id}`).
    Read-only exposure of an already-existing column; adds no new
    computation and changes no trading decision."""


class RecommendationSummaryResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    status: RecommendationStatus
    opened_at: datetime
    latest_version: RecommendationVersionResponse | None


class AgentOpinionResponse(BaseModel):
    stance: str | None
    structured_output: dict[str, Any]

    model_config = {"from_attributes": True}


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    role: AgentRole
    status: AgentRunStatus
    started_at: datetime | None
    completed_at: datetime | None
    opinion: AgentOpinionResponse | None


class CommitteeSessionDetailResponse(BaseModel):
    id: uuid.UUID
    instrument: InstrumentResponse
    triggered_by: str
    status: CommitteeSessionStatus
    started_at: datetime | None
    completed_at: datetime | None
    agent_runs: list[AgentRunResponse]
