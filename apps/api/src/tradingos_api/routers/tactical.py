"""Tactical-lane recommendations (Revision Prompt R3). Every
`Recommendation` here has `mode == TACTICAL` (ADR-046) — the sibling of
`/api/v1/investment`; the two never share a response shape (R3's
required test: "investment and tactical recommendations cannot be
confused"). Earnings-event detail lives in `/api/v1/earnings-events`,
the evidence a tactical earnings-strategy recommendation is built on."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.enums import RecommendationMode
from tradingos_api.models.order_authority import OrderProposal
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationInvalidationCondition,
    RecommendationVersion,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.tactical import (
    TacticalRecommendationSummaryResponse,
    TacticalRecommendationVersionResponse,
)

router = APIRouter(prefix="/api/v1/tactical", tags=["tactical"])


def _snapshot_str(snapshot: dict[str, object], key: str) -> str | None:
    value = snapshot.get(key)
    return value if isinstance(value, str) else None


def _latest_version(db: Session, recommendation_id: uuid.UUID) -> RecommendationVersion | None:
    return db.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == recommendation_id)
        .order_by(RecommendationVersion.version_number.desc())
    )


def _version_response(
    db: Session, version: RecommendationVersion
) -> TacticalRecommendationVersionResponse:
    snapshot: dict[str, object] = version.deterministic_inputs_snapshot or {}
    invalidation_condition = db.scalar(
        select(RecommendationInvalidationCondition).where(
            RecommendationInvalidationCondition.recommendation_version_id == version.id
        )
    )
    order_proposal = db.scalar(
        select(OrderProposal).where(OrderProposal.recommendation_version_id == version.id)
    )
    return TacticalRecommendationVersionResponse(
        id=version.id,
        version_number=version.version_number,
        lane_action=version.lane_action,
        confidence=version.confidence,
        score=version.score,
        rationale=version.rationale,
        horizon_days_min=version.horizon_days_min,
        horizon_days_max=version.horizon_days_max,
        review_date=version.review_date,
        generated_at=version.generated_at,
        entry_invalidation=(
            invalidation_condition.condition_text if invalidation_condition else None
        ),
        setup_and_event_phase=_snapshot_str(snapshot, "setup_and_event_phase"),
        key_catalyst=_snapshot_str(snapshot, "key_catalyst"),
        gap_risk=_snapshot_str(snapshot, "gap_risk"),
        liquidity_risk=_snapshot_str(snapshot, "liquidity_risk"),
        order_proposal_id=(order_proposal.id if order_proposal else None),
        order_proposal_status=(order_proposal.status.value if order_proposal else None),
    )


def _summary(db: Session, rec: Recommendation) -> TacticalRecommendationSummaryResponse:
    inst = db.get(Instrument, rec.instrument_id)
    assert inst is not None
    latest = _latest_version(db, rec.id)
    return TacticalRecommendationSummaryResponse(
        id=rec.id,
        instrument=InstrumentResponse.model_validate(inst),
        status=rec.status,
        opened_at=rec.opened_at,
        latest_version=_version_response(db, latest) if latest else None,
    )


@router.get("/recommendations", response_model=Page[TacticalRecommendationSummaryResponse])
def list_tactical_recommendations(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[TacticalRecommendationSummaryResponse]:
    stmt = (
        select(Recommendation)
        .where(Recommendation.mode == RecommendationMode.TACTICAL)
        .order_by(Recommendation.opened_at.desc())
    )
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    return Page(
        items=[_summary(db, rec) for rec in page_rows], total=total, limit=limit, offset=offset
    )


@router.get(
    "/recommendations/{recommendation_id}", response_model=TacticalRecommendationSummaryResponse
)
def get_tactical_recommendation(
    recommendation_id: uuid.UUID, db: Session = Depends(get_db)
) -> TacticalRecommendationSummaryResponse:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None or rec.mode != RecommendationMode.TACTICAL:
        raise HTTPException(status_code=404, detail="Tactical recommendation not found.")
    return _summary(db, rec)
