"""Settings and provider status (docs/API_CONTRACTS.md area 12)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import ProviderKind
from tradingos_api.models.identity import (
    InvestmentProfile,
    ProviderConfig,
    RiskPolicy,
    RiskPolicyVersion,
)
from tradingos_api.models.order_authority import ExecutionKillSwitchEvent
from tradingos_api.policy.order_authority import OrderAuthorityMode
from tradingos_api.schemas.settings import (
    InvestmentProfileResponse,
    KillSwitchStatusResponse,
    OperatingModeResponse,
    ProviderStatusResponse,
    RiskPolicyResponse,
    RiskPolicyUpdateRequest,
)

# HES-3's absolute hard ceiling ("configurable upper bound: 0.50%,
# reachable only after explicit policy approval") — this endpoint is the
# "safe policy-configuration screen" Revision Prompt 7 asks for, so it
# enforces the ceiling itself rather than trusting the caller not to
# drag it past what governance actually approved.
_ABSOLUTE_MAX_EARNINGS_RISK_BUDGET_PCT = Decimal("0.0050")

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


@router.get("/kill-switch-status", response_model=KillSwitchStatusResponse)
def get_kill_switch_status(db: Session = Depends(get_db)) -> KillSwitchStatusResponse:
    latest = db.scalar(
        select(ExecutionKillSwitchEvent).order_by(ExecutionKillSwitchEvent.activated_at.desc())
    )
    if latest is None:
        return KillSwitchStatusResponse(
            is_active=False, activated_by=None, activated_at=None, deactivated_at=None, reason=None
        )
    return KillSwitchStatusResponse(
        is_active=latest.deactivated_at is None,
        activated_by=latest.activated_by,
        activated_at=latest.activated_at,
        deactivated_at=latest.deactivated_at,
        reason=latest.reason,
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

    proposed_max = (
        payload.earnings_risk_budget_max_pct
        if payload.earnings_risk_budget_max_pct is not None
        else policy.earnings_risk_budget_max_pct
    )
    if proposed_max > _ABSOLUTE_MAX_EARNINGS_RISK_BUDGET_PCT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"earnings_risk_budget_max_pct cannot exceed "
                f"{_ABSOLUTE_MAX_EARNINGS_RISK_BUDGET_PCT} (HES-3's hard ceiling)."
            ),
        )
    proposed_budget = (
        payload.earnings_risk_budget_pct
        if payload.earnings_risk_budget_pct is not None
        else policy.earnings_risk_budget_pct
    )
    if proposed_budget > proposed_max:
        raise HTTPException(
            status_code=400,
            detail="earnings_risk_budget_pct cannot exceed earnings_risk_budget_max_pct.",
        )

    for field in (
        "risk_budget_pct",
        "max_position_pct",
        "max_sector_pct",
        "max_correlation",
        "speculative_position_pct_cap",
        "earnings_risk_budget_pct",
        "earnings_risk_budget_max_pct",
        "earnings_max_position_pct",
        "earnings_max_sector_pct",
        "earnings_max_concurrent_trades",
        "earnings_slippage_bps",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(policy, field, value)

    db.add(
        RiskPolicyVersion(
            risk_policy_id=policy.id,
            risk_budget_pct=policy.risk_budget_pct,
            max_position_pct=policy.max_position_pct,
            max_sector_pct=policy.max_sector_pct,
            max_correlation=policy.max_correlation,
            speculative_position_pct_cap=policy.speculative_position_pct_cap,
            changed_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.refresh(policy)
    return RiskPolicyResponse.model_validate(policy)
