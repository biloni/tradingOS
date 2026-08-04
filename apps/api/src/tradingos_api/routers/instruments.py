"""Instruments & symbol validation (docs/API_CONTRACTS.md area 1).

`POST /validate` never calls a live provider this pass ("do not
integrate external providers yet") — it checks the raw input against
already-`RESOLVED` instruments (case-insensitive exact ticker match) and
otherwise reports `QUARANTINED` with an honest reason naming that live
validation isn't wired up yet, rather than fabricating a plausible-looking
resolution (principle 4/5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.enums import InstrumentValidationStatus
from tradingos_api.models.security_master import Instrument, InstrumentValidationEvent
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import (
    InstrumentResponse,
    ValidateRequest,
    ValidateResponse,
    ValidationEventResponse,
)

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


@router.get("", response_model=Page[InstrumentResponse])
def list_instruments(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Case-insensitive ticker/name substring"),
    asset_type: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    sort: str = Query(default="ticker", pattern="^-?(ticker|name)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[InstrumentResponse]:
    stmt = select(Instrument)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(Instrument.ticker).like(like) | func.lower(Instrument.name).like(like)
        )
    if asset_type:
        stmt = stmt.where(Instrument.asset_type == asset_type)
    if active is not None:
        stmt = stmt.where(Instrument.active == active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_col = Instrument.name if sort.lstrip("-") == "name" else Instrument.ticker
    stmt = stmt.order_by(sort_col.desc() if sort.startswith("-") else sort_col.asc())
    stmt = stmt.limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    items = [InstrumentResponse.model_validate(r) for r in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{instrument_id}", response_model=InstrumentResponse)
def get_instrument(instrument_id: uuid.UUID, db: Session = Depends(get_db)) -> InstrumentResponse:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    return InstrumentResponse.model_validate(inst)


@router.get("/{instrument_id}/validation-events", response_model=list[ValidationEventResponse])
def get_validation_history(
    instrument_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[ValidationEventResponse]:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    rows = db.scalars(
        select(InstrumentValidationEvent)
        .where(InstrumentValidationEvent.canonical_instrument_id == instrument_id)
        .order_by(InstrumentValidationEvent.checked_at.desc())
    ).all()
    return [ValidationEventResponse.model_validate(r) for r in rows]


@router.post("/validate", response_model=ValidateResponse)
def validate_symbol(payload: ValidateRequest, db: Session = Depends(get_db)) -> ValidateResponse:
    raw = payload.raw_input.strip().upper()
    if not raw:
        raise HTTPException(status_code=422, detail="raw_input must not be blank.")

    inst = db.scalar(select(Instrument).where(func.upper(Instrument.ticker) == raw))
    if inst is not None:
        status = InstrumentValidationStatus.RESOLVED
        reason = "Matches an already-resolved instrument in the reference table."
    else:
        status = InstrumentValidationStatus.QUARANTINED
        reason = (
            "Live provider validation is not wired up yet (this phase is schema/API "
            "only) — cannot confirm this symbol against a real reference source."
        )

    db.add(
        InstrumentValidationEvent(
            raw_input=raw,
            status=status,
            canonical_instrument_id=inst.id if inst else None,
            reason=reason,
            source="api_manual_check",
            checked_at=datetime.now(UTC),
        )
    )
    db.commit()

    return ValidateResponse(
        status=status,
        instrument=InstrumentResponse.model_validate(inst) if inst else None,
        reason=reason,
    )
