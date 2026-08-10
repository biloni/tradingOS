from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from tradingos_api.models.enums import EventBacktestStrategyKey, ModelChangeProposalStatus


class CalibrationBinResponse(BaseModel):
    label: str
    sample_size: int
    is_adequate: bool
    observed_hit_rate_pct: Decimal | None
    ci_low_pct: Decimal | None
    ci_high_pct: Decimal | None
    brier_score: Decimal | None

    model_config = {"from_attributes": True}


class AgentEvaluationResponse(BaseModel):
    agent_role: str
    sample_size: int
    is_adequate: bool
    factual_accuracy_pct: Decimal | None
    evidence_coverage_pct: Decimal | None
    contradiction_detection_rate_pct: Decimal | None
    directional_usefulness_pct: Decimal | None
    contribution_after_deterministic_pct: Decimal | None
    contribution_sample_size: int
    minority_opinion_usefulness_pct: Decimal | None
    minority_sample_size: int

    model_config = {"from_attributes": True}


class EvidencePackage(BaseModel):
    """The pydantic-validated shape for a generic (non-strategy-parameter)
    proposal's evidence — Prompt 14's own "every proposal must contain"
    list, enforced at the API boundary before `services/change_governance.py::propose_change()`
    ever sees it (the same "validate at every write boundary" discipline
    CLAUDE.md's own SQLite-adaptation note establishes for this project)."""

    sample_size: int = Field(ge=0)
    evidence: list[str] = Field(min_length=1)
    current_version_snapshot: dict[str, Any]
    proposed_version_snapshot: dict[str, Any]
    economic_rationale: str = Field(min_length=1)
    train_results: dict[str, Any]
    validation_results: dict[str, Any]
    out_of_sample_results: dict[str, Any]
    walk_forward_results: dict[str, Any]
    sensitivity: dict[str, Any]
    costs: dict[str, Any]
    operational_risks: list[str]
    rollback_plan: str = Field(min_length=1)


class ProposeChangeRequest(BaseModel):
    subject_type: str
    subject_ref_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    evidence_package: EvidencePackage


class ProposeStrategyParameterChangeRequest(BaseModel):
    strategy_definition_id: uuid.UUID
    strategy_key: EventBacktestStrategyKey
    current_score_threshold: int
    proposed_score_threshold: int
    current_expected_move_threshold_pct: Decimal = Decimal(4)
    proposed_expected_move_threshold_pct: Decimal = Decimal(4)
    current_normal_risk_pct: Decimal = Decimal("0.50")
    proposed_normal_risk_pct: Decimal = Decimal("0.50")
    economic_rationale: str = Field(min_length=1)
    costs: dict[str, Any]
    operational_risks: list[str]
    rollback_plan: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DecisionRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    comment: str | None = None


class RejectRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    comment: str = Field(min_length=1)


class ActivateRequest(BaseModel):
    activated_by: str = Field(min_length=1)


class RollbackRequest(BaseModel):
    rolled_back_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ModelChangeApprovalResponse(BaseModel):
    id: uuid.UUID
    decision: ModelChangeProposalStatus
    comment: str | None
    decided_at: datetime

    model_config = {"from_attributes": True}


class ModelChangeProposalSummaryResponse(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_ref_id: uuid.UUID | None
    description: str
    status: ModelChangeProposalStatus
    proposed_at: datetime
    activated_at: datetime | None
    activated_by: str | None
    rolled_back_at: datetime | None
    rolled_back_by: str | None
    rollback_reason: str | None

    model_config = {"from_attributes": True}


class ModelChangeProposalDetailResponse(ModelChangeProposalSummaryResponse):
    evidence_package: dict[str, Any]
    approvals: list[ModelChangeApprovalResponse]


__all__ = [
    "ActivateRequest",
    "AgentEvaluationResponse",
    "CalibrationBinResponse",
    "DecisionRequest",
    "EvidencePackage",
    "ModelChangeApprovalResponse",
    "ModelChangeProposalDetailResponse",
    "ModelChangeProposalSummaryResponse",
    "ProposeChangeRequest",
    "ProposeStrategyParameterChangeRequest",
    "RejectRequest",
    "RollbackRequest",
]
