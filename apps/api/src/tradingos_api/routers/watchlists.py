"""Watchlists (docs/API_CONTRACTS.md area 2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.security_master import Instrument, Watchlist, WatchlistItem
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.watchlists import (
    WatchlistItemCreateRequest,
    WatchlistItemResponse,
    WatchlistItemUpdateRequest,
    WatchlistResponse,
)

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


def _item_response(item: WatchlistItem, instrument: Instrument) -> WatchlistItemResponse:
    return WatchlistItemResponse(
        id=item.id,
        watchlist_id=item.watchlist_id,
        instrument=InstrumentResponse.model_validate(instrument),
        tier=item.tier,
        priority=item.priority,
        active=item.active,
        notes=item.notes,
        monitoring_frequency=item.monitoring_frequency,
        added_at=item.added_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=list[WatchlistResponse])
def list_watchlists(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> list[WatchlistResponse]:
    rows = db.scalars(select(Watchlist).where(Watchlist.owner_user_id == owner_user_id)).all()
    return [WatchlistResponse.model_validate(r) for r in rows]


@router.get("/{watchlist_id}/items", response_model=Page[WatchlistItemResponse])
def list_watchlist_items(
    watchlist_id: uuid.UUID,
    db: Session = Depends(get_db),
    tier: int | None = Query(default=None),
    active: bool | None = Query(default=None),
    sort: str = Query(default="priority", pattern="^-?priority$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[WatchlistItemResponse]:
    if db.get(Watchlist, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="Watchlist not found.")

    stmt = (
        select(WatchlistItem, Instrument)
        .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
        .where(WatchlistItem.watchlist_id == watchlist_id)
    )
    if tier is not None:
        stmt = stmt.where(WatchlistItem.tier == tier)
    if active is not None:
        stmt = stmt.where(WatchlistItem.active == active)

    all_rows = list(db.execute(stmt).all())
    total = len(all_rows)
    order_desc = sort.startswith("-")
    all_rows.sort(key=lambda r: r[0].priority, reverse=order_desc)
    page_rows = all_rows[offset : offset + limit]

    return Page(
        items=[_item_response(item, inst) for item, inst in page_rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=201)
def add_watchlist_item(
    watchlist_id: uuid.UUID, payload: WatchlistItemCreateRequest, db: Session = Depends(get_db)
) -> WatchlistItemResponse:
    if db.get(Watchlist, watchlist_id) is None:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    instrument = db.get(Instrument, payload.instrument_id)
    if instrument is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unknown instrument_id — an instrument must be validated/resolved "
                "before it can join a watchlist."
            ),
        )
    existing = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.instrument_id == payload.instrument_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This instrument is already on the watchlist.")

    item = WatchlistItem(
        watchlist_id=watchlist_id,
        instrument_id=payload.instrument_id,
        tier=payload.tier,
        priority=payload.priority,
        active=True,
        notes=payload.notes,
        monitoring_frequency=payload.monitoring_frequency,
        added_at=datetime.now(UTC).date(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_response(item, instrument)


@router.patch("/items/{item_id}", response_model=WatchlistItemResponse)
def update_watchlist_item(
    item_id: uuid.UUID, payload: WatchlistItemUpdateRequest, db: Session = Depends(get_db)
) -> WatchlistItemResponse:
    item = db.get(WatchlistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    if item.updated_at != payload.expected_updated_at:
        raise HTTPException(
            status_code=409,
            detail=(
                "This item changed since you last read it "
                "(optimistic-concurrency mismatch). Reload and retry."
            ),
        )

    if payload.tier is not None:
        item.tier = payload.tier
    if payload.priority is not None:
        item.priority = payload.priority
    if payload.active is not None:
        item.active = payload.active
    if payload.notes is not None:
        item.notes = payload.notes
    if payload.monitoring_frequency is not None:
        item.monitoring_frequency = payload.monitoring_frequency

    db.commit()
    db.refresh(item)
    instrument = db.get(Instrument, item.instrument_id)
    assert instrument is not None
    return _item_response(item, instrument)
