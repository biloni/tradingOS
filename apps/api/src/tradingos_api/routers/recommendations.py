"""Recommendations & committee detail (docs/API_CONTRACTS.md area 4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.agents import (
    AgentDefinition,
    AgentOpinion,
    AgentRun,
    AgentVersion,
    CommitteeSession,
)
from tradingos_api.models.enums import RecommendationStatus
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationLevel,
    RecommendationVersion,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.recommendations import (
    AgentOpinionResponse,
    AgentRunResponse,
    CommitteeSessionDetailResponse,
    RecommendationLevelResponse,
    RecommendationSummaryResponse,
    RecommendationVersionResponse,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


def _latest_version(db: Session, recommendation_id: uuid.UUID) -> RecommendationVersion | None:
    return db.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == recommendation_id)
        .order_by(RecommendationVersion.version_number.desc())
    )


def _version_response(db: Session, version: RecommendationVersion) -> RecommendationVersionResponse:
    levels = db.scalars(
        select(RecommendationLevel).where(
            RecommendationLevel.recommendation_version_id == version.id
        )
    ).all()
    return RecommendationVersionResponse(
        id=version.id,
        version_number=version.version_number,
        action=version.action,
        confidence=version.confidence,
        score=version.score,
        rationale=version.rationale,
        generated_at=version.generated_at,
        levels=[RecommendationLevelResponse.model_validate(level_) for level_ in levels],
    )


@router.get("", response_model=Page[RecommendationSummaryResponse])
def list_recommendations(
    db: Session = Depends(get_db),
    status_filter: RecommendationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[RecommendationSummaryResponse]:
    stmt = select(Recommendation).order_by(Recommendation.opened_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Recommendation.status == status_filter)
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]

    items = []
    for rec in page_rows:
        inst = db.get(Instrument, rec.instrument_id)
        assert inst is not None
        latest = _latest_version(db, rec.id)
        items.append(
            RecommendationSummaryResponse(
                id=rec.id,
                instrument=InstrumentResponse.model_validate(inst),
                status=rec.status,
                opened_at=rec.opened_at,
                latest_version=_version_response(db, latest) if latest else None,
            )
        )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{recommendation_id}", response_model=RecommendationSummaryResponse)
def get_recommendation(
    recommendation_id: uuid.UUID, db: Session = Depends(get_db)
) -> RecommendationSummaryResponse:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    inst = db.get(Instrument, rec.instrument_id)
    assert inst is not None
    latest = _latest_version(db, rec.id)
    return RecommendationSummaryResponse(
        id=rec.id,
        instrument=InstrumentResponse.model_validate(inst),
        status=rec.status,
        opened_at=rec.opened_at,
        latest_version=_version_response(db, latest) if latest else None,
    )


@router.get("/committee-sessions/{session_id}", response_model=CommitteeSessionDetailResponse)
def get_committee_session(
    session_id: uuid.UUID, db: Session = Depends(get_db)
) -> CommitteeSessionDetailResponse:
    session_ = db.get(CommitteeSession, session_id)
    if session_ is None:
        raise HTTPException(status_code=404, detail="Committee session not found.")
    inst = db.get(Instrument, session_.instrument_id)
    assert inst is not None

    runs = db.scalars(select(AgentRun).where(AgentRun.committee_session_id == session_id)).all()
    run_responses = []
    for run in runs:
        agent_version = db.get(AgentVersion, run.agent_version_id)
        assert agent_version is not None
        agent_def = db.get(AgentDefinition, agent_version.agent_definition_id)
        assert agent_def is not None
        opinion = db.scalar(select(AgentOpinion).where(AgentOpinion.agent_run_id == run.id))
        run_responses.append(
            AgentRunResponse(
                id=run.id,
                role=agent_def.role,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                opinion=AgentOpinionResponse.model_validate(opinion) if opinion else None,
            )
        )

    return CommitteeSessionDetailResponse(
        id=session_.id,
        instrument=InstrumentResponse.model_validate(inst),
        triggered_by=session_.triggered_by,
        status=session_.status,
        started_at=session_.started_at,
        completed_at=session_.completed_at,
        agent_runs=run_responses,
    )
