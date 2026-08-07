"""Deterministic dual-lane analytics scoring layer (Revision Prompt 5,
additive to Phase 8/R3/R4). No recommendation, order, or LLM-generated
content lives here — this bounded context is strictly "what did the
deterministic math say," never "what should happen next."

`FeatureComponentResult` is the one generic, diagnostic-grade record of
a single scored component (one of the tactical 8, one of the investment
lane's component scores, or one of the post-earnings confirmation
features) — the same generic subject_type/subject_id shape
`AuditEvent`/`DataQualityEvent`/`ProviderIngestionRecord` already
established (ADR-015), reused here so the diagnostic UI's "show every
component, value, pass/fail, source, cutoff, version, and missing
state" requirement has one table to query regardless of which parent
snapshot type (`EarningsFeatureSnapshot`, `PostEarningsConfirmationSnapshot`,
`InvestmentQualityFeatureSnapshot`) the component belongs to.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import FeatureComponentStatus


class FeatureComponentResult(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only — a re-run of a scoring pass writes new rows against
    the new parent snapshot id, never edits a prior component result.
    `value` is nullable (a `MISSING_DATA`/`CAPABILITY_UNAVAILABLE` row
    has no value to report); `detail` carries the explanation code/human
    text COMMON ANALYTICS requires alongside every structured value."""

    __tablename__ = "feature_component_results"
    __table_args__ = (
        sa.Index("ix_feature_component_results_subject", "subject_type", "subject_id"),
    )

    subject_type: Mapped[str] = mapped_column(sa.String(50))
    subject_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True))
    component_key: Mapped[str] = mapped_column(sa.String(50))
    component_order: Mapped[int] = mapped_column(sa.Integer)
    value: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 6), nullable=True)
    status: Mapped[FeatureComponentStatus] = mapped_column(
        sa.Enum(FeatureComponentStatus, name="feature_component_status")
    )
    source: Mapped[str] = mapped_column(sa.String(40))
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    calculation_version: Mapped[str] = mapped_column(sa.String(20))
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class InvestmentQualityFeatureSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """The Investment lane's parent snapshot — deliberately holds no
    single opaque score. Its `FeatureComponentResult` children (linked
    via `subject_type="InvestmentQualityFeatureSnapshot"`) carry the
    component scores (revenue/earnings growth, margin trend,
    balance-sheet/cash-flow quality, valuation vs. history/sector/growth,
    earnings revision direction, business/sector durability, long-term
    relative strength, catalysts/event risks, portfolio diversification/
    concentration); `hard_disqualified` is this snapshot's own explicit
    veto flag, independent of any component score — a disqualifier is
    binary and named, never averaged away by strong scores elsewhere."""

    __tablename__ = "investment_quality_feature_snapshots"
    __table_args__ = (
        sa.Index("ix_investment_quality_feature_snapshots_lookup", "instrument_id", "as_of"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    evidence_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    calculation_version: Mapped[str] = mapped_column(sa.String(20))
    hard_disqualified: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    disqualification_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


__all__ = [
    "FeatureComponentResult",
    "InvestmentQualityFeatureSnapshot",
]
