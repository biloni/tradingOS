"""Upcoming earnings calendar, earnings-event detail, and post-event
confirmation (Revision Prompt R3, docs/HYBRID_EARNINGS_STRATEGY.md)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.market_evidence import (
    EarningsActual,
    EarningsConsensusSnapshot,
    EarningsEvent,
    EarningsFeatureSnapshot,
    EarningsGuidanceItem,
    EventExpectedMoveSnapshot,
    PostEarningsConfirmationSnapshot,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.earnings import (
    EarningsActualResponse,
    EarningsConsensusSnapshotResponse,
    EarningsEventCalendarRowResponse,
    EarningsEventDetailResponse,
    EarningsFeatureSnapshotResponse,
    EarningsGuidanceItemResponse,
    EventExpectedMoveSnapshotResponse,
    PostEarningsConfirmationSnapshotResponse,
)
from tradingos_api.schemas.instruments import InstrumentResponse

router = APIRouter(prefix="/api/v1/earnings-events", tags=["earnings-events"])


@router.get("/calendar", response_model=list[EarningsEventCalendarRowResponse])
def get_earnings_calendar(
    db: Session = Depends(get_db),
    days: int = Query(default=14, ge=1, le=180),
    as_of: date | None = Query(default=None),
) -> list[EarningsEventCalendarRowResponse]:
    """Every earnings event with `report_date` in `[as_of, as_of + days]`
    (defaults `as_of` to today), ascending — the morning plan's upcoming-
    earnings section reads from this same query."""
    start = as_of or date.today()
    end = start + timedelta(days=days)
    rows = db.scalars(
        select(EarningsEvent)
        .where(EarningsEvent.report_date >= start, EarningsEvent.report_date <= end)
        .order_by(EarningsEvent.report_date.asc())
    ).all()
    items = []
    for row in rows:
        inst = db.get(Instrument, row.instrument_id)
        assert inst is not None
        items.append(
            EarningsEventCalendarRowResponse(
                id=row.id,
                instrument=InstrumentResponse.model_validate(inst),
                report_date=row.report_date,
                timing_category=row.timing_category,
                verified_date=row.verified_date,
                confidence=row.confidence,
            )
        )
    return items


@router.get("/{earnings_event_id}", response_model=EarningsEventDetailResponse)
def get_earnings_event(
    earnings_event_id: uuid.UUID, db: Session = Depends(get_db)
) -> EarningsEventDetailResponse:
    event = db.get(EarningsEvent, earnings_event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Earnings event not found.")
    inst = db.get(Instrument, event.instrument_id)
    assert inst is not None

    consensus = db.scalars(
        select(EarningsConsensusSnapshot)
        .where(EarningsConsensusSnapshot.earnings_event_id == event.id)
        .order_by(EarningsConsensusSnapshot.as_of.desc())
    ).all()
    guidance = db.scalars(
        select(EarningsGuidanceItem).where(EarningsGuidanceItem.earnings_event_id == event.id)
    ).all()
    actuals = db.scalars(
        select(EarningsActual).where(EarningsActual.earnings_event_id == event.id)
    ).all()
    latest_move = db.scalar(
        select(EventExpectedMoveSnapshot)
        .where(EventExpectedMoveSnapshot.earnings_event_id == event.id)
        .order_by(EventExpectedMoveSnapshot.as_of.desc())
    )
    latest_feature = db.scalar(
        select(EarningsFeatureSnapshot)
        .where(EarningsFeatureSnapshot.earnings_event_id == event.id)
        .order_by(EarningsFeatureSnapshot.as_of.desc())
    )

    return EarningsEventDetailResponse(
        id=event.id,
        instrument=InstrumentResponse.model_validate(inst),
        fiscal_period=event.fiscal_period,
        report_date=event.report_date,
        verified_date=event.verified_date,
        exchange_local_date=event.exchange_local_date,
        timing_category=event.timing_category,
        verification_source=event.verification_source,
        expected_report_period=event.expected_report_period,
        confidence=event.confidence,
        eps_estimate=event.eps_estimate,
        eps_actual=event.eps_actual,
        consensus_snapshots=[
            EarningsConsensusSnapshotResponse.model_validate(c) for c in consensus
        ],
        guidance_items=[EarningsGuidanceItemResponse.model_validate(g) for g in guidance],
        actuals=[EarningsActualResponse.model_validate(a) for a in actuals],
        latest_expected_move=(
            EventExpectedMoveSnapshotResponse.model_validate(latest_move) if latest_move else None
        ),
        latest_feature_snapshot=(
            EarningsFeatureSnapshotResponse.model_validate(latest_feature)
            if latest_feature
            else None
        ),
    )


@router.get(
    "/{earnings_event_id}/post-event-confirmation",
    response_model=PostEarningsConfirmationSnapshotResponse,
)
def get_post_event_confirmation(
    earnings_event_id: uuid.UUID, db: Session = Depends(get_db)
) -> PostEarningsConfirmationSnapshotResponse:
    if db.get(EarningsEvent, earnings_event_id) is None:
        raise HTTPException(status_code=404, detail="Earnings event not found.")
    snapshot = db.scalar(
        select(PostEarningsConfirmationSnapshot)
        .where(PostEarningsConfirmationSnapshot.earnings_event_id == earnings_event_id)
        .order_by(PostEarningsConfirmationSnapshot.as_of.desc())
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail="No post-event confirmation snapshot exists for this event yet."
        )
    return PostEarningsConfirmationSnapshotResponse.model_validate(snapshot)
