from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import ProviderKind, RiskTolerance


class ProviderStatusResponse(BaseModel):
    """Never exposes a secret value — `is_enabled` and `config_metadata`
    only (docs/SECURITY.md); whether a real credential is actually
    present is reported as a derived boolean, not the credential itself."""

    id: uuid.UUID
    provider_kind: ProviderKind
    provider_name: str
    is_enabled: bool
    config_metadata: dict[str, Any]
    has_credential_configured: bool

    model_config = {"from_attributes": True}


class InvestmentProfileResponse(BaseModel):
    starting_capital_usd: Decimal
    risk_tolerance: RiskTolerance
    holding_period_min_days: int
    holding_period_max_days: int

    model_config = {"from_attributes": True}


class RiskPolicyResponse(BaseModel):
    risk_budget_pct: Decimal
    max_position_pct: Decimal
    max_sector_pct: Decimal
    max_correlation: Decimal
    speculative_position_pct_cap: Decimal
    # Revision Prompt 7 (HES-3) — earnings-specific ceilings, deliberately
    # separate from the general-purpose fields above.
    earnings_risk_budget_pct: Decimal
    earnings_risk_budget_max_pct: Decimal
    earnings_max_position_pct: Decimal
    earnings_max_sector_pct: Decimal
    earnings_max_concurrent_trades: int
    earnings_slippage_bps: Decimal

    model_config = {"from_attributes": True}


class RiskPolicyUpdateRequest(BaseModel):
    risk_budget_pct: Decimal | None = None
    max_position_pct: Decimal | None = None
    max_sector_pct: Decimal | None = None
    max_correlation: Decimal | None = None
    speculative_position_pct_cap: Decimal | None = None
    earnings_risk_budget_pct: Decimal | None = None
    earnings_risk_budget_max_pct: Decimal | None = None
    earnings_max_position_pct: Decimal | None = None
    earnings_max_sector_pct: Decimal | None = None
    earnings_max_concurrent_trades: int | None = None
    earnings_slippage_bps: Decimal | None = None


class OperatingModeResponse(BaseModel):
    """`mode` is one of `policy.order_authority.OrderAuthorityMode`'s
    four values; `environment_label` is the coarser RESEARCH/PAPER/LIVE
    band PROJECT_INSTRUCTIONS.md's environment-banner requirement names.
    Since Revision Prompt 10, `can_submit_orders` reflects the
    **effective** mode (`services/order_authority.py::compute_effective_mode()`
    — kill-switch-aware), not just the configured one;
    `assert_order_authorized()` is now called for real from
    `routers/order_authority.py::submit_order_approval()`."""

    mode: str
    environment_label: str
    can_submit_orders: bool


class KillSwitchStatusResponse(BaseModel):
    """Revision Prompt R3, OA-9. Active iff the most recent
    `ExecutionKillSwitchEvent` has no `deactivated_at` yet. No event
    row at all means the kill switch has never been activated."""

    is_active: bool
    activated_by: str | None
    activated_at: datetime | None
    deactivated_at: datetime | None
    reason: str | None
