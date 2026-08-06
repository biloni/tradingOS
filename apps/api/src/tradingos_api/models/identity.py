"""Identity & preferences bounded context (docs/ARCHITECTURE.md context 1
of the refinement's new contexts) — Phase 8, schema only, no auth.

Single-user system (ADR-007, unchanged) — `UserProfile` exists so every
other table can carry real row ownership (the refinement brief: "add row
ownership even though the initial system is single-user") rather than
inventing ownership later against already-populated tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import NotificationChannel, ProviderKind, RiskTolerance


class UserProfile(UUIDPkMixin, CreatedAtMixin, Base):
    """The one user. `services/identity.py`'s `get_or_create_default_user()`
    lazily creates the single row, the same pattern the shipped MVP already
    used for `PaperPortfolio` (ADR-013)."""

    __tablename__ = "user_profile"

    display_name: Mapped[str] = mapped_column(sa.String(120))
    timezone: Mapped[str] = mapped_column(sa.String(64), default="America/New_York")


class InvestmentProfile(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """The persona-level facts from docs/PRODUCT_REQUIREMENTS.md — starting
    capital, risk tolerance, holding-period horizon. Distinct from
    `RiskPolicy` below: this is *who the user is*; `RiskPolicy` is *the
    numeric limits currently in force*."""

    __tablename__ = "investment_profile"

    starting_capital_usd: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6), default=Decimal(10000))
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(
        sa.Enum(RiskTolerance, name="risk_tolerance"), default=RiskTolerance.AGGRESSIVE
    )
    holding_period_min_days: Mapped[int] = mapped_column(sa.Integer, default=2)
    holding_period_max_days: Mapped[int] = mapped_column(sa.Integer, default=10)


class RiskPolicy(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """The numeric limits the deterministic gates (docs/ARCHITECTURE.md
    context 6, future phase) read at run time. Kept separate from
    `StrategyVersion.config` (ADR-036/045): a `StrategyVersion` is a
    proposed-and-approved *system* configuration subject to principle 16's
    review gate; `RiskPolicy` is the user's own stated preference/ceiling
    that a strategy version's sizing math must additionally respect. This
    is a single current-settings row (mutated in place via `TimestampMixin`),
    not versioned/approved like a strategy — a user changing their own risk
    tolerance doesn't need a backtest comparison to take effect."""

    __tablename__ = "risk_policy"

    risk_budget_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4), default=Decimal("0.0100"))
    max_position_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4), default=Decimal("0.2000"))
    max_sector_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4), default=Decimal("0.4000"))
    max_correlation: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4), default=Decimal("0.7000"))
    speculative_position_pct_cap: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 4), default=Decimal("0.0500")
    )


class RiskPolicyVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Revision Prompt R3 — append-only snapshot history paralleling the
    singleton, mutable-in-place `risk_policy` row above. Every time
    `PATCH /api/v1/settings/risk-policy` changes a field, this revision's
    service layer also writes one of these rows, so "what were the limits
    on a given past date" is answerable without `risk_policy` itself
    needing to become a versioned/approved entity (which it deliberately
    is not — see `RiskPolicy`'s own docstring)."""

    __tablename__ = "risk_policy_versions"
    __table_args__ = (sa.Index("ix_risk_policy_versions_lookup", "risk_policy_id", "changed_at"),)

    risk_policy_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("risk_policy.id")
    )
    risk_budget_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    max_position_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    max_sector_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    max_correlation: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    speculative_position_pct_cap: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class NotificationPreference(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """One row per (channel, category). MVP only ever has `IN_APP` rows
    enabled (BLOCKING_DECISIONS.md #9) — the schema doesn't assume that
    stays true forever."""

    __tablename__ = "notification_preferences"
    __table_args__ = (sa.UniqueConstraint("owner_user_id", "channel", "category"),)

    channel: Mapped[NotificationChannel] = mapped_column(
        sa.Enum(NotificationChannel, name="notification_channel")
    )
    category: Mapped[str] = mapped_column(sa.String(50))
    enabled: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class ProviderConfig(UUIDPkMixin, TimestampMixin, Base):
    """Non-secret provider settings only — base URL, display name, which
    capability it's wired for, whether it's currently enabled. **No secret
    value (API key, token) is ever a column on this table** — every real
    credential lives in `apps/api/.env` (docs/SECURITY.md, unchanged); this
    table exists purely so `/api/v1/settings/providers` (docs/UX_MAP.md-
    equivalent, Phase 8's settings endpoint) has something non-secret to
    report status from (e.g. "Alpaca: configured" vs. "Alpaca: not
    configured" — a boolean derived from whether the env var is set, not a
    display of the value itself)."""

    __tablename__ = "provider_config"

    provider_kind: Mapped[ProviderKind] = mapped_column(sa.Enum(ProviderKind, name="provider_kind"))
    provider_name: Mapped[str] = mapped_column(sa.String(80))
    is_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)


__all__ = [
    "InvestmentProfile",
    "NotificationPreference",
    "ProviderConfig",
    "RiskPolicy",
    "RiskPolicyVersion",
    "UserProfile",
]
