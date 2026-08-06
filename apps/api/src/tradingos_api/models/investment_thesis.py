"""Investment thesis bounded context (Revision Prompt R3, additive to
Phase 8/ADR-050). One `InvestmentThesis` per `Recommendation` whose
`mode` is `INVESTMENT` — the durable "why we hold this" record DQ-1
requires (valuation range, thesis, horizon, review date, catalysts,
risks, thesis-break conditions), versioned the same way
`RecommendationVersion` already is: the thesis identity is stable and
mutates its `status` in place, but its actual content lives on immutable,
append-only `InvestmentThesisVersion` rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import ThesisStatus


class InvestmentThesis(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """The stable identity, one per Investment-lane `Recommendation`
    (unique `recommendation_id`) — mirrors `Recommendation`/
    `RecommendationVersion`'s split: this row's `status` is the current
    lifecycle state; the actual valuation/thesis text lives on the
    latest `InvestmentThesisVersion`, never here."""

    __tablename__ = "investment_theses"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), unique=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    status: Mapped[ThesisStatus] = mapped_column(
        sa.Enum(ThesisStatus, name="thesis_status"), default=ThesisStatus.ACTIVE
    )


class InvestmentThesisVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Immutable once written — a thesis revision creates the next
    version number, never edits a prior one, the same append-only
    discipline as `RecommendationVersion`."""

    __tablename__ = "investment_thesis_versions"
    __table_args__ = (sa.UniqueConstraint("investment_thesis_id", "version_number"),)

    investment_thesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_theses.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(sa.Integer)
    valuation_low: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    valuation_mid: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    valuation_high: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    thesis_text: Mapped[str] = mapped_column(sa.Text)
    horizon_days_min: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    horizon_days_max: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    review_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ValuationSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """An independently-timestamped valuation data point (e.g. a DCF or
    comp-based fair-value estimate) — append-only, distinct from
    `InvestmentThesisVersion.valuation_*` (the thesis's own stated range)
    since a valuation snapshot can be refreshed on its own schedule
    without the thesis narrative itself changing."""

    __tablename__ = "valuation_snapshots"
    __table_args__ = (sa.Index("ix_valuation_snapshots_lookup", "investment_thesis_id", "as_of"),)

    investment_thesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_theses.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    method: Mapped[str] = mapped_column(sa.String(40))
    fair_value_low: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    fair_value_mid: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    fair_value_high: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(40))
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class ThesisCatalyst(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "thesis_catalysts"

    investment_thesis_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_thesis_versions.id"), index=True
    )
    catalyst_text: Mapped[str] = mapped_column(sa.Text)
    expected_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)


class ThesisRisk(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "thesis_risks"

    investment_thesis_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_thesis_versions.id"), index=True
    )
    risk_text: Mapped[str] = mapped_column(sa.Text)


class ThesisReviewEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only log of periodic human reviews of a thesis (distinct
    from `ThesisStatusHistory`: a review can conclude "still intact"
    without any status transition at all)."""

    __tablename__ = "thesis_review_events"

    investment_thesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_theses.id"), index=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ThesisStatusHistory(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only lifecycle audit trail for `InvestmentThesis.status`
    transitions, guarded by `THESIS_STATUS_TRANSITIONS`
    (`services/lifecycle.py::assert_transition_allowed`) — the same
    pattern as `RecommendationStatusEvent`."""

    __tablename__ = "thesis_status_history"

    investment_thesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("investment_theses.id"), index=True
    )
    from_status: Mapped[ThesisStatus | None] = mapped_column(
        sa.Enum(ThesisStatus, name="thesis_status"), nullable=True
    )
    to_status: Mapped[ThesisStatus] = mapped_column(sa.Enum(ThesisStatus, name="thesis_status"))
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


__all__ = [
    "InvestmentThesis",
    "InvestmentThesisVersion",
    "ThesisCatalyst",
    "ThesisReviewEvent",
    "ThesisRisk",
    "ThesisStatusHistory",
    "ValuationSnapshot",
]
