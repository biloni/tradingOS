"""Committee endpoints (Revision Prompt 6). Running a committee is a
synchronous, explicitly-triggered, human-reviewed action — there is no
scheduled/background trigger anywhere in this router ("do not schedule
production runs or submit orders"). `GET /sessions/{id}` is the review
screen: every role's full agent-contract output, cost, and latency, so a
human can audit a run before acting on its recommendation."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.db.session import get_db
from tradingos_api.models.agents import AgentDefinition, AgentOpinion, AgentRun, AgentVersion
from tradingos_api.models.agents import CommitteeSession as CommitteeSessionModel
from tradingos_api.models.operations import ModelCallRecord
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.committee import (
    CommitteeRunRequest,
    CommitteeRunResponse,
    LaneConclusionResponse,
    RoleRunResponse,
    SideBySideResponse,
)
from tradingos_api.services.committee_orchestrator import (
    CommitteeInputBundle,
    EvidenceItem,
    run_committee,
)
from tradingos_api.services.side_by_side import LaneConclusion, get_side_by_side_view

router = APIRouter(prefix="/api/v1/committee", tags=["committee"])

_LANES: dict[str, RecommendationMode] = {
    "investment": RecommendationMode.INVESTMENT,
    "tactical": RecommendationMode.TACTICAL,
}


def _lane_or_404(lane: str) -> RecommendationMode:
    resolved = _LANES.get(lane.lower())
    if resolved is None:
        raise HTTPException(status_code=404, detail="lane must be 'investment' or 'tactical'")
    return resolved


@router.post("/{lane}/{instrument_id}/run", response_model=CommitteeRunResponse)
def run_committee_endpoint(
    lane: str,
    instrument_id: uuid.UUID,
    payload: CommitteeRunRequest,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> CommitteeRunResponse:
    resolved_lane = _lane_or_404(lane)
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")

    bundle = CommitteeInputBundle(
        instrument_id=instrument_id,
        symbol=payload.symbol,
        as_of=payload.evidence_cutoff,
        evidence_cutoff=payload.evidence_cutoff,
        evidence=[
            EvidenceItem(
                evidence_id=e.evidence_id, evidence_type=e.evidence_type, summary=e.summary
            )
            for e in payload.evidence
        ],
        deterministic_feature_ids=payload.deterministic_feature_ids,
        deterministic_summary=payload.deterministic_summary,
        hard_veto_active=payload.hard_veto_active,
        hard_veto_reason=payload.hard_veto_reason,
        watchlist_item_id=payload.watchlist_item_id,
    )
    result = run_committee(
        db,
        lane=resolved_lane,
        bundle=bundle,
        llm=llm,
        cost_ceiling_usd=payload.cost_ceiling_usd,
        per_call_timeout_seconds=payload.per_call_timeout_seconds,
        triggered_by=payload.triggered_by,
    )
    db.commit()

    total_cost = sum((rr.outcome.cost_usd for rr in result.role_runs), Decimal(0))
    return CommitteeRunResponse(
        session_id=result.session.id,
        lane=resolved_lane.value,
        status=result.session.status.value,
        role_runs=[
            RoleRunResponse(
                role=rr.role.role.value,
                display_name=rr.role.display_name,
                status=rr.outcome.status,
                error_detail=rr.outcome.error_detail,
                output=(rr.outcome.output.model_dump(mode="json") if rr.outcome.output else None),
                model=rr.outcome.model,
                input_tokens=rr.outcome.input_tokens,
                output_tokens=rr.outcome.output_tokens,
                latency_ms=rr.outcome.latency_ms,
                cost_usd=rr.outcome.cost_usd,
            )
            for rr in result.role_runs
        ],
        total_cost_usd=total_cost,
        recommendation_id=(result.recommendation.id if result.recommendation else None),
        lane_action=(
            result.recommendation_version.lane_action if result.recommendation_version else None
        ),
        veto_override_applied=result.veto_override_applied,
    )


@router.get("/sessions/{session_id}", response_model=CommitteeRunResponse)
def get_committee_session(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> CommitteeRunResponse:
    """The review screen — reconstructs a past run's full detail from
    the persisted audit trail rather than re-running anything."""
    session = db.get(CommitteeSessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Committee session not found.")

    runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.committee_session_id == session_id)
        .order_by(AgentRun.created_at.asc())
    ).all()

    role_runs: list[RoleRunResponse] = []
    total_cost = Decimal(0)
    for run in runs:
        version = db.get(AgentVersion, run.agent_version_id)
        definition = db.get(AgentDefinition, version.agent_definition_id) if version else None
        opinion = db.scalar(select(AgentOpinion).where(AgentOpinion.agent_run_id == run.id))
        call_record = db.scalar(
            select(ModelCallRecord).where(ModelCallRecord.agent_run_id == run.id)
        )
        cost = call_record.cost_usd if call_record else Decimal(0)
        total_cost += cost
        role_runs.append(
            RoleRunResponse(
                role=(definition.role.value if definition else "UNKNOWN"),
                display_name=(definition.name if definition else "Unknown role"),
                status=("SUCCEEDED" if run.status.value == "SUCCEEDED" else "FAILED"),
                error_detail=run.error_detail,
                output=(opinion.structured_output if opinion else None),
                model=(call_record.model if call_record else None),
                input_tokens=(call_record.input_tokens if call_record else 0),
                output_tokens=(call_record.output_tokens if call_record else 0),
                latency_ms=(call_record.latency_ms or 0) if call_record else 0,
                cost_usd=cost,
            )
        )

    return CommitteeRunResponse(
        session_id=session.id,
        lane=(session.mode.value if session.mode else "INVESTMENT"),
        status=session.status.value,
        role_runs=role_runs,
        total_cost_usd=total_cost,
        recommendation_id=None,
        lane_action=None,
        veto_override_applied=False,
    )


@router.get("/side-by-side/{instrument_id}", response_model=SideBySideResponse)
def get_side_by_side(instrument_id: uuid.UUID, db: Session = Depends(get_db)) -> SideBySideResponse:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    view = get_side_by_side_view(db, instrument_id)

    def _to_response(conclusion: LaneConclusion | None) -> LaneConclusionResponse | None:
        if conclusion is None:
            return None
        return LaneConclusionResponse(
            recommendation_id=conclusion.recommendation_id,
            lane_action=conclusion.lane_action,
            confidence=conclusion.confidence,
            rationale=conclusion.rationale,
            horizon_days_min=conclusion.horizon_days_min,
            horizon_days_max=conclusion.horizon_days_max,
            review_date=conclusion.review_date,
            generated_at=conclusion.generated_at,
        )

    return SideBySideResponse(
        instrument_id=instrument_id,
        investment=_to_response(view.investment),
        tactical=_to_response(view.tactical),
        divergence_explanation=view.divergence_explanation,
    )


__all__ = ["router"]
