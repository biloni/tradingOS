"""Trade journal and reviews (docs/API_CONTRACTS.md area 7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.enums import TradeStatus
from tradingos_api.models.execution import Trade, TradeNote, TradeThesis
from tradingos_api.models.learning import TradeReview
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.journal import (
    TradeDetailResponse,
    TradeNoteCreateRequest,
    TradeNoteResponse,
    TradeReviewCreateRequest,
    TradeReviewResponse,
    TradeThesisResponse,
)

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


def _trade_detail(db: Session, trade: Trade) -> TradeDetailResponse:
    inst = db.get(Instrument, trade.instrument_id)
    assert inst is not None
    thesis = db.scalar(select(TradeThesis).where(TradeThesis.trade_id == trade.id))
    notes = db.scalars(
        select(TradeNote)
        .where(TradeNote.trade_id == trade.id)
        .order_by(TradeNote.created_at.desc())
    ).all()
    reviews = db.scalars(
        select(TradeReview)
        .where(TradeReview.trade_id == trade.id)
        .order_by(TradeReview.reviewed_at.desc())
    ).all()
    return TradeDetailResponse(
        id=trade.id,
        account_id=trade.account_id,
        instrument=InstrumentResponse.model_validate(inst),
        status=trade.status,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        quantity=trade.quantity,
        realized_pnl=trade.realized_pnl,
        thesis=TradeThesisResponse.model_validate(thesis) if thesis else None,
        notes=[TradeNoteResponse.model_validate(n) for n in notes],
        reviews=[TradeReviewResponse.model_validate(r) for r in reviews],
    )


@router.get("/trades", response_model=Page[TradeDetailResponse])
def list_trades(
    db: Session = Depends(get_db),
    account_id: uuid.UUID | None = Query(default=None),
    status_filter: TradeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[TradeDetailResponse]:
    stmt = select(Trade).order_by(Trade.opened_at.desc())
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    if status_filter is not None:
        stmt = stmt.where(Trade.status == status_filter)
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    items = [_trade_detail(db, t) for t in page_rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/trades/{trade_id}", response_model=TradeDetailResponse)
def get_trade(trade_id: uuid.UUID, db: Session = Depends(get_db)) -> TradeDetailResponse:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    return _trade_detail(db, trade)


@router.post("/trades/{trade_id}/notes", response_model=TradeDetailResponse, status_code=201)
def add_note(
    trade_id: uuid.UUID, payload: TradeNoteCreateRequest, db: Session = Depends(get_db)
) -> TradeDetailResponse:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    db.add(TradeNote(trade_id=trade_id, note_text=payload.note_text))
    db.commit()
    return _trade_detail(db, trade)


@router.post("/trades/{trade_id}/reviews", response_model=TradeDetailResponse, status_code=201)
def add_review(
    trade_id: uuid.UUID, payload: TradeReviewCreateRequest, db: Session = Depends(get_db)
) -> TradeDetailResponse:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    if trade.status != TradeStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Only a closed trade can be reviewed.")
    db.add(
        TradeReview(
            trade_id=trade_id,
            rating=payload.rating,
            review_text=payload.review_text,
            reviewed_at=datetime.now(UTC),
        )
    )
    db.commit()
    return _trade_detail(db, trade)
