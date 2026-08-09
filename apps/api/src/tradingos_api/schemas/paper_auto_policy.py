"""Schemas for the `PaperAutoPolicyVersion` CRUD surface (Revision
Prompt 10, OA-4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import KillSwitchBehavior


class PaperAutoPolicyCreateRequest(BaseModel):
    """Every field Revision Prompt 10 names the user must choose.
    `enabled` defaults `False` — creating a version does not itself turn
    automation on; a caller must set it explicitly, matching "disabled
    by default." Defaults for the rest match "the default eligible
    strategy is the conservative earnings strategy with score at least
    6.\""""

    enabled: bool = False
    eligible_strategy_families: list[str] = ["EARNINGS_PRE_EVENT"]
    min_score: Decimal = Decimal(6)
    max_orders_per_day: int = 1
    max_daily_notional: Decimal
    max_per_order_risk_pct: Decimal
    allowed_time_windows: list[dict[str, Any]] = []
    allowed_order_types: list[str] = ["MARKET", "LIMIT"]
    kill_switch_behavior: KillSwitchBehavior = KillSwitchBehavior.HALT_AND_CANCEL_OPEN
    created_by: str


class PaperAutoPolicyResponse(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    version_number: int
    enabled: bool
    eligible_strategy_families: list[str]
    min_score: Decimal
    max_orders_per_day: int
    max_daily_notional: Decimal
    max_per_order_risk_pct: Decimal
    allowed_time_windows: list[dict[str, Any]]
    allowed_order_types: list[str]
    kill_switch_behavior: KillSwitchBehavior
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}
