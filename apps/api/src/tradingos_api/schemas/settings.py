from __future__ import annotations

import uuid
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

    model_config = {"from_attributes": True}


class RiskPolicyUpdateRequest(BaseModel):
    risk_budget_pct: Decimal | None = None
    max_position_pct: Decimal | None = None
    max_sector_pct: Decimal | None = None
    max_correlation: Decimal | None = None
    speculative_position_pct_cap: Decimal | None = None
