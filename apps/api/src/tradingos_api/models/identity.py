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
    used for `PaperPortfolio` (ADR-013).

    `password_hash` (Revision Prompt 16, ADR-066 — supersedes ADR-007's
    "no authentication" for the paper-beta release): `scrypt$<salt_hex>$<hash_hex>`,
    never a plaintext password or a reversible encryption. Nullable — a
    freshly-seeded user has no password until `scripts/set_password.py`
    (the one-time bootstrap CLI, never an HTTP endpoint) sets one;
    `routers/auth.py::login()` rejects login with a clear message while
    it's `None` rather than treating `None` as "no password required.\""""

    __tablename__ = "user_profile"

    display_name: Mapped[str] = mapped_column(sa.String(120))
    timezone: Mapped[str] = mapped_column(sa.String(64), default="America/New_York")
    password_hash: Mapped[str | None] = mapped_column(sa.String(255), default=None)


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
    # Revision Prompt 7 (HES-3) — earnings-specific ceilings, deliberately
    # separate fields rather than overloading the general fields above:
    # HES-3's own text is explicit that these are "materially smaller
    # than the standard" general-purpose numbers, not a replacement for
    # them. Same fractional convention as every field above (0.0025 =
    # 0.25%) — `services/position_sizing.py` takes whole-number percent
    # (0.25 meaning 0.25%) and the pipeline converts (`* 100`) at the
    # boundary; see `services/recommendation_pipeline.py`.
    earnings_risk_budget_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 4), default=Decimal("0.0025")
    )
    earnings_risk_budget_max_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 4), default=Decimal("0.0050")
    )
    earnings_max_position_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 4), default=Decimal("0.1500")
    )
    earnings_max_sector_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(6, 4), default=Decimal("0.2500")
    )
    earnings_max_concurrent_trades: Mapped[int] = mapped_column(sa.Integer, default=3)
    earnings_slippage_bps: Mapped[Decimal] = mapped_column(
        sa.Numeric(8, 4), default=Decimal("5.0000")
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


class Session(UUIDPkMixin, CreatedAtMixin, Base):
    """A server-side, revocable login session (Revision Prompt 16, ADR-066).

    `token_hash` — SHA-256 hex of the raw session token — is the only
    thing ever stored; the raw token itself lives only in the client's
    httpOnly cookie and this one response, never written to a log or a
    database column, so a database leak alone can never be replayed as a
    live session (`core/auth.py::hash_token()`). `stepped_up_at` is
    separate from `created_at`/`last_seen_at`: a normal session proves
    "this browser logged in recently," but Prompt 16's step-up
    requirement for kill switch / cancel-all / mode changes / approval
    decisions needs "the password was re-entered recently," a strictly
    narrower and separately-expiring fact (`core/auth.py::STEP_UP_TTL`).
    """

    __tablename__ = "sessions"
    __table_args__ = (sa.Index("ix_sessions_token_hash", "token_hash", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("user_profile.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64))
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    stepped_up_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), default=None)
    user_agent: Mapped[str | None] = mapped_column(sa.String(255), default=None)
    ip_address: Mapped[str | None] = mapped_column(sa.String(64), default=None)


__all__ = [
    "InvestmentProfile",
    "NotificationPreference",
    "ProviderConfig",
    "RiskPolicy",
    "Session",
    "RiskPolicyVersion",
    "UserProfile",
]
