"""Settings and provider status (docs/API_CONTRACTS.md area 12)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import ProviderKind
from tradingos_api.models.identity import InvestmentProfile, ProviderConfig, RiskPolicy
from tradingos_api.policy.order_authority import OrderAuthorityMode
from tradingos_api.schemas.settings import (
    InvestmentProfileResponse,
    OperatingModeResponse,
    ProviderStatusResponse,
    RiskPolicyResponse,
    RiskPolicyUpdateRequest,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_ENVIRONMENT_LABEL_BY_MODE: dict[OrderAuthorityMode, str] = {
    OrderAuthorityMode.RESEARCH_ONLY: "RESEARCH",
    OrderAuthorityMode.PAPER_MANUAL_APPROVAL: "PAPER",
    OrderAuthorityMode.PAPER_AUTO_POLICY: "PAPER",
    OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER: "LIVE",
}


@router.get("/operating-mode", response_model=OperatingModeResponse)
def get_operating_mode() -> OperatingModeResponse:
    """Revision Prompt R2 scaffold — the one server-side source of truth
    the frontend's environment banner and operating-mode status component
    read (PROJECT_INSTRUCTIONS.md's v2 amendment: "whose display value
    comes from the API, not client storage"). Reports configuration only;
    `assert_order_authorized()` (policy/order_authority.py, R0) is not
    wired into any order-mutating router yet, so `can_submit_orders` here
    is informational, not an active gate — see
    docs/ORDER_AUTHORITY_MODEL.md for the traceability to when it becomes
    one."""
    try:
        mode = OrderAuthorityMode(get_settings().operating_mode)
    except ValueError:
        mode = OrderAuthorityMode.RESEARCH_ONLY
    return OperatingModeResponse(
        mode=mode.value,
        environment_label=_ENVIRONMENT_LABEL_BY_MODE[mode],
        can_submit_orders=mode is not OrderAuthorityMode.RESEARCH_ONLY,
    )


@router.get("/providers", response_model=list[ProviderStatusResponse])
def list_provider_status(db: Session = Depends(get_db)) -> list[ProviderStatusResponse]:
    settings = get_settings()
    has_alpaca = bool(settings.alpaca_api_key_id and settings.alpaca_api_secret_key)
    credential_present = {
        ProviderKind.MARKET_DATA: has_alpaca,
        ProviderKind.BROKER: has_alpaca,
        ProviderKind.LLM: bool(settings.anthropic_api_key),
        ProviderKind.NEWS: False,
        ProviderKind.FUNDAMENTALS: False,
    }
    rows = db.scalars(select(ProviderConfig)).all()
    return [
        ProviderStatusResponse(
            id=r.id,
            provider_kind=r.provider_kind,
            provider_name=r.provider_name,
            is_enabled=r.is_enabled,
            config_metadata=r.config_metadata,
            has_credential_configured=credential_present.get(r.provider_kind, False),
        )
        for r in rows
    ]


@router.get("/investment-profile", response_model=InvestmentProfileResponse)
def get_investment_profile(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> InvestmentProfileResponse:
    profile = db.scalar(
        select(InvestmentProfile).where(InvestmentProfile.owner_user_id == owner_user_id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="No investment profile configured.")
    return InvestmentProfileResponse.model_validate(profile)


@router.get("/risk-policy", response_model=RiskPolicyResponse)
def get_risk_policy(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> RiskPolicyResponse:
    policy = db.scalar(select(RiskPolicy).where(RiskPolicy.owner_user_id == owner_user_id))
    if policy is None:
        raise HTTPException(status_code=404, detail="No risk policy configured.")
    return RiskPolicyResponse.model_validate(policy)


@router.patch("/risk-policy", response_model=RiskPolicyResponse)
def update_risk_policy(
    payload: RiskPolicyUpdateRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RiskPolicyResponse:
    policy = db.scalar(select(RiskPolicy).where(RiskPolicy.owner_user_id == owner_user_id))
    if policy is None:
        raise HTTPException(status_code=404, detail="No risk policy configured.")

    for field in (
        "risk_budget_pct",
        "max_position_pct",
        "max_sector_pct",
        "max_correlation",
        "speculative_position_pct_cap",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(policy, field, value)

    db.commit()
    db.refresh(policy)
    return RiskPolicyResponse.model_validate(policy)
