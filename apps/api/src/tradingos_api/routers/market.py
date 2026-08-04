"""Market overview & data freshness, and per-instrument bars/indicators
(docs/API_CONTRACTS.md area 3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.market_evidence import (
    MarketBar,
    MarketRegimeSnapshot,
    TechnicalIndicatorSnapshot,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.market import (
    BarResponse,
    FreshnessRow,
    IndicatorSnapshotResponse,
    MarketOverviewResponse,
    RegimeResponse,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])

STALE_AFTER = timedelta(hours=36)


def _latest_bar_subquery(db: Session, instrument_id):  # type: ignore[no-untyped-def]
    return db.execute(
        select(MarketBar)
        .where(MarketBar.instrument_id == instrument_id)
        .order_by(MarketBar.as_of.desc(), MarketBar.ingested_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.get("/overview", response_model=MarketOverviewResponse)
def get_overview(db: Session = Depends(get_db)) -> MarketOverviewResponse:
    regime = db.scalar(select(MarketRegimeSnapshot).order_by(MarketRegimeSnapshot.as_of.desc()))
    instrument_ids = db.scalars(select(Instrument.id).where(Instrument.active.is_(True))).all()
    stale_count = 0
    now = datetime.now(UTC)
    for iid in instrument_ids:
        bar = _latest_bar_subquery(db, iid)
        if bar is None or (now - bar.ingested_at) > STALE_AFTER:
            stale_count += 1
    return MarketOverviewResponse(
        regime=RegimeResponse.model_validate(regime) if regime else None,
        tracked_instrument_count=len(instrument_ids),
        stale_instrument_count=stale_count,
    )


@router.get("/freshness", response_model=list[FreshnessRow])
def get_freshness(db: Session = Depends(get_db)) -> list[FreshnessRow]:
    now = datetime.now(UTC)
    rows: list[FreshnessRow] = []
    for inst in db.scalars(select(Instrument).where(Instrument.active.is_(True))).all():
        bar = _latest_bar_subquery(db, inst.id)
        rows.append(
            FreshnessRow(
                instrument_id=inst.id,
                ticker=inst.ticker,
                latest_bar_as_of=bar.as_of if bar else None,
                latest_bar_ingested_at=bar.ingested_at if bar else None,
                is_stale=(bar is None or (now - bar.ingested_at) > STALE_AFTER),
            )
        )
    rows.sort(key=lambda r: r.ticker)
    return rows


@router.get("/instruments/{ticker}/bars", response_model=list[BarResponse])
def get_bars(
    ticker: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=500),
) -> list[BarResponse]:
    inst = db.scalar(select(Instrument).where(func.upper(Instrument.ticker) == ticker.upper()))
    if inst is None:
        raise HTTPException(status_code=404, detail="Unknown ticker.")
    rows = db.scalars(
        select(MarketBar)
        .where(MarketBar.instrument_id == inst.id)
        .order_by(MarketBar.as_of.desc())
        .limit(limit)
    ).all()
    return [BarResponse.model_validate(r) for r in reversed(rows)]


@router.get("/instruments/{ticker}/indicators", response_model=list[IndicatorSnapshotResponse])
def get_indicators(ticker: str, db: Session = Depends(get_db)) -> list[IndicatorSnapshotResponse]:
    inst = db.scalar(select(Instrument).where(func.upper(Instrument.ticker) == ticker.upper()))
    if inst is None:
        raise HTTPException(status_code=404, detail="Unknown ticker.")
    latest_as_of = db.scalar(
        select(func.max(TechnicalIndicatorSnapshot.as_of)).where(
            TechnicalIndicatorSnapshot.instrument_id == inst.id
        )
    )
    if latest_as_of is None:
        return []
    rows = db.scalars(
        select(TechnicalIndicatorSnapshot).where(
            TechnicalIndicatorSnapshot.instrument_id == inst.id,
            TechnicalIndicatorSnapshot.as_of == latest_as_of,
        )
    ).all()
    return [IndicatorSnapshotResponse.model_validate(r) for r in rows]
