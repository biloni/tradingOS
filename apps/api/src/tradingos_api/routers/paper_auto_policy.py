"""`PaperAutoPolicyVersion` CRUD (Revision Prompt 10, OA-4) — the
"user must choose eligible strategies, maximum orders per day, maximum
daily notional, maximum per-order risk, allowed time windows, order
types, minimum score, and kill-switch behavior" configuration screen.
Every write here creates a new, append-only version — never edits a
previous one — mirroring `RiskPolicyVersion`'s pattern."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.order_authority import PaperAutoPolicyVersion
from tradingos_api.schemas.paper_auto_policy import (
    PaperAutoPolicyCreateRequest,
    PaperAutoPolicyResponse,
)

router = APIRouter(prefix="/api/v1/paper-auto-policy", tags=["paper-auto-policy"])


@router.get("", response_model=PaperAutoPolicyResponse)
def get_current_auto_policy(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> PaperAutoPolicyResponse:
    """The latest version, whatever its `enabled` value — unlike
    `services/paper_auto_policy.py::get_active_auto_policy()` (which
    returns `None` for a disabled one), this endpoint always shows the
    current configuration so a user can see what they'd be re-enabling."""
    latest = db.scalar(
        select(PaperAutoPolicyVersion)
        .where(PaperAutoPolicyVersion.owner_user_id == owner_user_id)
        .order_by(PaperAutoPolicyVersion.version_number.desc())
    )
    if latest is None:
        raise HTTPException(
            status_code=404, detail="No paper auto-policy has ever been configured."
        )
    return PaperAutoPolicyResponse.model_validate(latest)


@router.post("", response_model=PaperAutoPolicyResponse, status_code=201)
def create_auto_policy_version(
    payload: PaperAutoPolicyCreateRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PaperAutoPolicyResponse:
    prior_max = db.scalar(
        select(PaperAutoPolicyVersion.version_number)
        .where(PaperAutoPolicyVersion.owner_user_id == owner_user_id)
        .order_by(PaperAutoPolicyVersion.version_number.desc())
    )
    version = PaperAutoPolicyVersion(
        owner_user_id=owner_user_id,
        version_number=(prior_max or 0) + 1,
        enabled=payload.enabled,
        eligible_strategy_families=payload.eligible_strategy_families,
        min_score=payload.min_score,
        max_orders_per_day=payload.max_orders_per_day,
        max_daily_notional=payload.max_daily_notional,
        max_per_order_risk_pct=payload.max_per_order_risk_pct,
        allowed_time_windows=payload.allowed_time_windows,
        allowed_order_types=payload.allowed_order_types,
        kill_switch_behavior=payload.kill_switch_behavior,
        created_by=payload.created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return PaperAutoPolicyResponse.model_validate(version)


@router.post("/disable", response_model=PaperAutoPolicyResponse)
def disable_auto_policy(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> PaperAutoPolicyResponse:
    """Convenience action: a new version identical to the latest one
    except `enabled=False` — "disabled by default" applies just as much
    to turning it back off as to never having configured it."""
    latest = db.scalar(
        select(PaperAutoPolicyVersion)
        .where(PaperAutoPolicyVersion.owner_user_id == owner_user_id)
        .order_by(PaperAutoPolicyVersion.version_number.desc())
    )
    if latest is None:
        raise HTTPException(
            status_code=404, detail="No paper auto-policy has ever been configured."
        )
    version = PaperAutoPolicyVersion(
        owner_user_id=owner_user_id,
        version_number=latest.version_number + 1,
        enabled=False,
        eligible_strategy_families=latest.eligible_strategy_families,
        min_score=latest.min_score,
        max_orders_per_day=latest.max_orders_per_day,
        max_daily_notional=latest.max_daily_notional,
        max_per_order_risk_pct=latest.max_per_order_risk_pct,
        allowed_time_windows=latest.allowed_time_windows,
        allowed_order_types=latest.allowed_order_types,
        kill_switch_behavior=latest.kill_switch_behavior,
        created_by=latest.created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return PaperAutoPolicyResponse.model_validate(version)
