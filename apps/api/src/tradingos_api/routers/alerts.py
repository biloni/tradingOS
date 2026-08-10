"""Alerts (docs/API_CONTRACTS.md area 9)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import AlertStatus
from tradingos_api.models.operations import Alert
from tradingos_api.schemas.alerts import AlertResponse, AlertUpdateRequest
from tradingos_api.schemas.common import Page
from tradingos_api.services.alerts_engine import expire_stale_alerts, transition_alert_status
from tradingos_api.services.lifecycle import InvalidTransitionError

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertResponse])
def list_alerts(
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
    status_filter: AlertStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[AlertResponse]:
    """Lazily expires stale alerts before every read (`expire_stale_alerts()`)
    so an `OPEN` filter never returns something past its `expires_at` —
    Prompt 11's "expiring" requirement is enforced at the one place every
    alert list is served from, not left to a background job that may not
    exist yet."""
    expire_stale_alerts(db, now=datetime.now(UTC))
    db.commit()
    stmt = (
        select(Alert)
        .where(Alert.owner_user_id == owner_user_id)
        .order_by(Alert.triggered_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Alert.status == status_filter)
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    items = [AlertResponse.model_validate(a) for a in page_rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{alert_id}", response_model=AlertResponse)
def update_alert_status(
    alert_id: uuid.UUID,
    payload: AlertUpdateRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> AlertResponse:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if alert.updated_at != payload.expected_updated_at:
        raise HTTPException(
            status_code=409,
            detail="This alert changed since you last read it (optimistic-concurrency mismatch).",
        )
    try:
        transition_alert_status(
            db,
            alert,
            to_status=payload.status,
            changed_at=datetime.now(UTC),
            changed_by=str(owner_user_id),
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(alert)
    return AlertResponse.model_validate(alert)
