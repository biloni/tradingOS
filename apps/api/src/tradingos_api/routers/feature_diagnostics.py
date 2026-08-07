"""Diagnostic UI endpoints for the deterministic dual-lane analytics
engine (Revision Prompt 5). Read-only throughout — no scoring, no
persistence, and no recommendation logic happens here; these endpoints
only render what `services/persist_feature_results.py` already wrote.
Every response shows, per component: value, pass/fail/missing state,
source, calculation version, and as-of time — the prompt's literal
"show every component, value, pass/fail, source, cutoff, version, and
missing state" requirement."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.feature_scoring import (
    FeatureComponentResult,
    InvestmentQualityFeatureSnapshot,
)
from tradingos_api.models.market_evidence import (
    EarningsFeatureSnapshot,
    PostEarningsConfirmationSnapshot,
)
from tradingos_api.schemas.feature_diagnostics import (
    FeatureComponentEntry,
    InvestmentQualitySnapshotResponse,
    PostEarningsConfirmationSnapshotResponse,
    TacticalScoreSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/feature-diagnostics", tags=["feature-diagnostics"])


def _components_for(
    db: Session, subject_type: str, subject_id: uuid.UUID
) -> list[FeatureComponentEntry]:
    rows = db.scalars(
        select(FeatureComponentResult)
        .where(
            FeatureComponentResult.subject_type == subject_type,
            FeatureComponentResult.subject_id == subject_id,
        )
        .order_by(FeatureComponentResult.component_order.asc())
    ).all()
    return [
        FeatureComponentEntry(
            component_key=row.component_key,
            component_order=row.component_order,
            value=row.value,
            status=row.status.value,
            source=row.source,
            detail=row.detail,
            calculation_version=row.calculation_version,
            as_of=row.as_of,
        )
        for row in rows
    ]


@router.get("/components/{subject_type}/{subject_id}", response_model=list[FeatureComponentEntry])
def get_components_for_subject(
    subject_type: str, subject_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[FeatureComponentEntry]:
    """Generic lookup — works for any parent snapshot type without the
    caller needing to know which lane produced it, mirroring
    `/provider-diagnostics/lineage/{subject_type}/{subject_id}`'s shape."""
    components = _components_for(db, subject_type, subject_id)
    if not components:
        raise HTTPException(
            status_code=404, detail="No component results recorded for this subject."
        )
    return components


@router.get("/tactical/{earnings_event_id}/latest", response_model=TacticalScoreSnapshotResponse)
def get_latest_tactical_score(
    earnings_event_id: uuid.UUID, db: Session = Depends(get_db)
) -> TacticalScoreSnapshotResponse:
    snapshot = db.scalar(
        select(EarningsFeatureSnapshot)
        .where(EarningsFeatureSnapshot.earnings_event_id == earnings_event_id)
        .order_by(EarningsFeatureSnapshot.as_of.desc())
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail="No tactical score snapshot recorded for this earnings event."
        )
    return TacticalScoreSnapshotResponse(
        id=snapshot.id,
        earnings_event_id=snapshot.earnings_event_id,
        as_of=snapshot.as_of,
        evidence_cutoff=snapshot.evidence_cutoff,
        total_score=snapshot.total_score,
        calculation_version=snapshot.calculation_version,
        components=_components_for(db, "EarningsFeatureSnapshot", snapshot.id),
    )


@router.get("/investment/{instrument_id}/latest", response_model=InvestmentQualitySnapshotResponse)
def get_latest_investment_quality(
    instrument_id: uuid.UUID, db: Session = Depends(get_db)
) -> InvestmentQualitySnapshotResponse:
    snapshot = db.scalar(
        select(InvestmentQualityFeatureSnapshot)
        .where(InvestmentQualityFeatureSnapshot.instrument_id == instrument_id)
        .order_by(InvestmentQualityFeatureSnapshot.as_of.desc())
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No investment-quality snapshot recorded for this instrument.",
        )
    return InvestmentQualitySnapshotResponse(
        id=snapshot.id,
        instrument_id=snapshot.instrument_id,
        as_of=snapshot.as_of,
        evidence_cutoff=snapshot.evidence_cutoff,
        hard_disqualified=snapshot.hard_disqualified,
        disqualification_reason=snapshot.disqualification_reason,
        calculation_version=snapshot.calculation_version,
        components=_components_for(db, "InvestmentQualityFeatureSnapshot", snapshot.id),
    )


@router.get(
    "/post-earnings/{earnings_event_id}/latest",
    response_model=PostEarningsConfirmationSnapshotResponse,
)
def get_latest_post_earnings_confirmation(
    earnings_event_id: uuid.UUID, db: Session = Depends(get_db)
) -> PostEarningsConfirmationSnapshotResponse:
    snapshot = db.scalar(
        select(PostEarningsConfirmationSnapshot)
        .where(PostEarningsConfirmationSnapshot.earnings_event_id == earnings_event_id)
        .order_by(PostEarningsConfirmationSnapshot.as_of.desc())
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No post-earnings confirmation snapshot recorded for this earnings event.",
        )
    return PostEarningsConfirmationSnapshotResponse(
        id=snapshot.id,
        earnings_event_id=snapshot.earnings_event_id,
        as_of=snapshot.as_of,
        evidence_cutoff=snapshot.evidence_cutoff,
        results_gate_passed=snapshot.results_gate_passed,
        guidance_gate_passed=snapshot.guidance_gate_passed,
        market_reaction_gate_passed=snapshot.market_reaction_gate_passed,
        all_gates_passed=snapshot.all_gates_passed,
        components=_components_for(db, "PostEarningsConfirmationSnapshot", snapshot.id),
    )
