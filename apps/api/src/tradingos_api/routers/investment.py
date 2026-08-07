"""Investment-lane recommendations and thesis detail (Revision Prompt
R3). Every `Recommendation` here has `mode == INVESTMENT` (ADR-046) —
`/api/v1/tactical` is the sibling router for the other lane, and the two
never share a response so a client can never confuse which lane a row
came from (R3's required test: "investment and tactical recommendations
cannot be confused")."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.enums import RecommendationMode
from tradingos_api.models.investment_thesis import (
    InvestmentThesis,
    InvestmentThesisVersion,
    ThesisCatalyst,
    ThesisRisk,
    ThesisStatusHistory,
    ValuationSnapshot,
)
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationInvalidationCondition,
    RecommendationVersion,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.investment import (
    InvestmentRecommendationSummaryResponse,
    InvestmentThesisDetailResponse,
    InvestmentThesisVersionResponse,
    ThesisCatalystResponse,
    ThesisRiskResponse,
    ThesisStatusHistoryResponse,
    ValuationSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/investment", tags=["investment"])


def _snapshot_str(snapshot: dict[str, object], key: str) -> str | None:
    value = snapshot.get(key)
    return value if isinstance(value, str) else None


def _thesis_detail(db: Session, thesis: InvestmentThesis) -> InvestmentThesisDetailResponse:
    inst = db.get(Instrument, thesis.instrument_id)
    assert inst is not None
    latest_version = db.scalar(
        select(InvestmentThesisVersion)
        .where(InvestmentThesisVersion.investment_thesis_id == thesis.id)
        .order_by(InvestmentThesisVersion.version_number.desc())
    )
    version_response = None
    if latest_version is not None:
        catalysts = db.scalars(
            select(ThesisCatalyst).where(
                ThesisCatalyst.investment_thesis_version_id == latest_version.id
            )
        ).all()
        risks = db.scalars(
            select(ThesisRisk).where(ThesisRisk.investment_thesis_version_id == latest_version.id)
        ).all()
        version_response = InvestmentThesisVersionResponse(
            id=latest_version.id,
            version_number=latest_version.version_number,
            valuation_low=latest_version.valuation_low,
            valuation_mid=latest_version.valuation_mid,
            valuation_high=latest_version.valuation_high,
            thesis_text=latest_version.thesis_text,
            horizon_days_min=latest_version.horizon_days_min,
            horizon_days_max=latest_version.horizon_days_max,
            review_date=latest_version.review_date,
            generated_at=latest_version.generated_at,
            catalysts=[ThesisCatalystResponse.model_validate(c) for c in catalysts],
            risks=[ThesisRiskResponse.model_validate(r) for r in risks],
        )

    snapshots = db.scalars(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.investment_thesis_id == thesis.id)
        .order_by(ValuationSnapshot.as_of.desc())
    ).all()
    history = db.scalars(
        select(ThesisStatusHistory)
        .where(ThesisStatusHistory.investment_thesis_id == thesis.id)
        .order_by(ThesisStatusHistory.occurred_at.desc())
    ).all()

    # Revision Prompt 7 — the remaining plan fields, read from the
    # recommendation's latest `RecommendationVersion` (thesis-break
    # conditions have their own child table; the rest live in
    # `deterministic_inputs_snapshot`).
    latest_rec_version = db.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == thesis.recommendation_id)
        .order_by(RecommendationVersion.version_number.desc())
    )
    thesis_break_conditions: list[str] = []
    snapshot: dict[str, object] = {}
    if latest_rec_version is not None:
        conditions = db.scalars(
            select(RecommendationInvalidationCondition).where(
                RecommendationInvalidationCondition.recommendation_version_id
                == latest_rec_version.id
            )
        ).all()
        thesis_break_conditions = [c.condition_text for c in conditions]
        snapshot = latest_rec_version.deterministic_inputs_snapshot or {}

    return InvestmentThesisDetailResponse(
        id=thesis.id,
        recommendation_id=thesis.recommendation_id,
        instrument=InstrumentResponse.model_validate(inst),
        status=thesis.status,
        latest_version=version_response,
        valuation_snapshots=[ValuationSnapshotResponse.model_validate(s) for s in snapshots],
        status_history=[ThesisStatusHistoryResponse.model_validate(h) for h in history],
        thesis_break_conditions=thesis_break_conditions,
        lane_action=(latest_rec_version.lane_action if latest_rec_version else None),
        preferred_accumulation_zone=_snapshot_str(snapshot, "preferred_accumulation_zone"),
        tranche_plan=_snapshot_str(snapshot, "tranche_plan"),
        proposed_max_allocation_pct=_snapshot_str(snapshot, "proposed_max_allocation_pct"),
        portfolio_role=_snapshot_str(snapshot, "portfolio_role"),
        why_investment_not_trade=_snapshot_str(snapshot, "why_investment_not_trade"),
    )


@router.get("/recommendations", response_model=Page[InvestmentRecommendationSummaryResponse])
def list_investment_recommendations(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[InvestmentRecommendationSummaryResponse]:
    stmt = (
        select(Recommendation)
        .where(Recommendation.mode == RecommendationMode.INVESTMENT)
        .order_by(Recommendation.opened_at.desc())
    )
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]

    items = []
    for rec in page_rows:
        inst = db.get(Instrument, rec.instrument_id)
        assert inst is not None
        thesis = db.scalar(
            select(InvestmentThesis).where(InvestmentThesis.recommendation_id == rec.id)
        )
        items.append(
            InvestmentRecommendationSummaryResponse(
                id=rec.id,
                instrument=InstrumentResponse.model_validate(inst),
                status=rec.status,
                opened_at=rec.opened_at,
                thesis_id=thesis.id if thesis else None,
            )
        )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/recommendations/{recommendation_id}", response_model=InvestmentRecommendationSummaryResponse
)
def get_investment_recommendation(
    recommendation_id: uuid.UUID, db: Session = Depends(get_db)
) -> InvestmentRecommendationSummaryResponse:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None or rec.mode != RecommendationMode.INVESTMENT:
        raise HTTPException(status_code=404, detail="Investment recommendation not found.")
    inst = db.get(Instrument, rec.instrument_id)
    assert inst is not None
    thesis = db.scalar(select(InvestmentThesis).where(InvestmentThesis.recommendation_id == rec.id))
    return InvestmentRecommendationSummaryResponse(
        id=rec.id,
        instrument=InstrumentResponse.model_validate(inst),
        status=rec.status,
        opened_at=rec.opened_at,
        thesis_id=thesis.id if thesis else None,
    )


@router.get("/theses/{thesis_id}", response_model=InvestmentThesisDetailResponse)
def get_investment_thesis(
    thesis_id: uuid.UUID, db: Session = Depends(get_db)
) -> InvestmentThesisDetailResponse:
    thesis = db.get(InvestmentThesis, thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail="Investment thesis not found.")
    return _thesis_detail(db, thesis)
