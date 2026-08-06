"""Recommendation bounded context (ADR-043 supersedes `models/recommendation.py`'s
`Recommendation`). Splits the shipped MVP's single mutable-ish row into a
stable identity (`Recommendation`) plus immutable, append-only snapshots
(`RecommendationVersion`) — "preserve recommendation snapshots so later
model changes cannot rewrite history" is the direct design driver: a
`RecommendationVersion` row, once created, is never updated.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    RecommendationAction,
    RecommendationConfidence,
    RecommendationLevelKind,
    RecommendationMode,
    RecommendationStatus,
)


class Recommendation(UUIDPkMixin, CreatedAtMixin, Base):
    """The stable identity — "our current call on this instrument." Its
    `status` is the *current* lifecycle state; the actual content (action,
    confidence, rationale) lives on the latest `RecommendationVersion`,
    never on this row, so recomputing a recommendation never overwrites
    what was said before.

    `mode` (Revision Prompt R3, ADR-046/ADR-050) distinguishes an
    Investment (~3-24 month) identity from a Tactical (~1-10 day) one —
    schema-backed version of `policy.recommendation_modes.RecommendationMode`
    (R0). Additive: existing Phase 8 rows are backfilled to `TACTICAL`
    (the shipped MVP's swing-trade framing) by this revision's migration;
    every new row must set it explicitly. A symbol may have both an
    Investment and a Tactical `Recommendation` row at once — they are
    always two separate rows, never one row with two lanes (PM-2)."""

    __tablename__ = "recommendations"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    watchlist_item_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("watchlist_items.id"), nullable=True
    )
    mode: Mapped[RecommendationMode] = mapped_column(
        sa.Enum(RecommendationMode, name="recommendation_mode"),
        default=RecommendationMode.TACTICAL,
    )
    opened_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[RecommendationStatus] = mapped_column(
        sa.Enum(RecommendationStatus, name="recommendation_status"),
        default=RecommendationStatus.ACTIVE,
    )

    __table_args__ = (sa.Index("ix_recommendations_mode_status", "mode", "status"),)


class RecommendationVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Immutable once written (never updated, only superseded by a new
    version row with the next `version_number`) — the actual auditable
    content: what was recommended, at what confidence, why, and from what
    deterministic inputs. `committee_session_id` is nullable so a
    version produced by the shipped MVP's simpler 4-signal path (before
    the committee exists) is representable too.

    Revision Prompt R3 additive columns: `lane_action` holds the mode-
    scoped action value (`policy.recommendation_modes.InvestmentAction`/
    `TacticalAction`, R0) as a plain string rather than a native Postgres
    enum — a single column can't cleanly type-check against "one of two
    enums depending on another column's value" in Postgres without a
    trigger, so this is validated at the API layer (zod/pydantic
    equivalent) against the parent `Recommendation.mode`, the same
    SQLite-adaptation-style trade-off this project already documents
    elsewhere for mode-conditional vocabularies. The original `action`
    column (six-value `RecommendationAction`) is untouched for backward
    compatibility and is no longer written by new code, only read."""

    __tablename__ = "recommendation_versions"
    __table_args__ = (sa.UniqueConstraint("recommendation_id", "version_number"),)

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), index=True
    )
    committee_session_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("committee_sessions.id"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(sa.Integer)
    action: Mapped[RecommendationAction] = mapped_column(
        sa.Enum(RecommendationAction, name="recommendation_action")
    )
    lane_action: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    confidence: Mapped[RecommendationConfidence] = mapped_column(
        sa.Enum(RecommendationConfidence, name="recommendation_confidence")
    )
    score: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    rationale: Mapped[str] = mapped_column(sa.Text)
    deterministic_inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(
        PORTABLE_JSON, default=dict
    )
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    horizon_days_min: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    horizon_days_max: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    review_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)


class RecommendationLevel(UUIDPkMixin, CreatedAtMixin, Base):
    """Entry/stop/target/trailing prices for one recommendation version
    (FR-21's ATR+structure+gap+catalyst+trailing composite lands here as
    concrete price levels, once that logic exists — this pass just models
    where it's stored). `basis` is a short human-readable explanation
    (e.g. "1.5x ATR_14 below entry") kept alongside the raw price so a
    past level is self-explanatory without re-deriving it."""

    __tablename__ = "recommendation_levels"

    recommendation_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), index=True
    )
    kind: Mapped[RecommendationLevelKind] = mapped_column(
        sa.Enum(RecommendationLevelKind, name="recommendation_level_kind")
    )
    price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    basis: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class RecommendationStatusEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only lifecycle audit trail for `Recommendation.status`
    transitions (principle 9), guarded by
    `services/lifecycle.py::assert_transition_allowed` against
    `RECOMMENDATION_TRANSITIONS`."""

    __tablename__ = "recommendation_status_events"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), index=True
    )
    from_status: Mapped[RecommendationStatus | None] = mapped_column(
        sa.Enum(RecommendationStatus, name="recommendation_status"), nullable=True
    )
    to_status: Mapped[RecommendationStatus] = mapped_column(
        sa.Enum(RecommendationStatus, name="recommendation_status")
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ConfidenceCalibrationRecord(UUIDPkMixin, CreatedAtMixin, Base):
    """Phase 2 (docs/MVP_PLAN.md) — modeled now, populated once a real
    sample of closed, outcome-tracked recommendations exists (principle
    15). `hit_rate` is nullable because a period with zero closed
    recommendations in a given confidence band has nothing to compute yet."""

    __tablename__ = "confidence_calibration_records"

    confidence_band: Mapped[RecommendationConfidence] = mapped_column(
        sa.Enum(RecommendationConfidence, name="recommendation_confidence")
    )
    period_start: Mapped[date] = mapped_column(sa.Date)
    period_end: Mapped[date] = mapped_column(sa.Date)
    sample_size: Mapped[int] = mapped_column(sa.Integer, default=0)
    hit_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class RecommendationInvalidationCondition(UUIDPkMixin, CreatedAtMixin, Base):
    """DQ-1/DQ-2's "objective thesis-break conditions" / "cancellation
    conditions," one row per condition (a version may state more than
    one) — Revision Prompt R3. Append-only, tied to the immutable version
    it was stated on; never edited once written."""

    __tablename__ = "recommendation_invalidation_conditions"

    recommendation_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), index=True
    )
    condition_text: Mapped[str] = mapped_column(sa.Text)


class RecommendationAttribution(UUIDPkMixin, CreatedAtMixin, Base):
    """Links a `PositionLot` or a `Trade` back to the exact recommendation
    version (and lane) that produced it — Revision Prompt R3's
    `recommendation_attribution`. Exactly one of `position_lot_id`/
    `trade_id` is set per row (enforced at the API/service layer, not a
    DB constraint, matching this codebase's existing preference for
    application-level invariants over exotic CHECK constraints). This is
    the concrete mechanism behind docs/ARCHITECTURE.md's R1 answer to
    "how are investment and tactical positions attributed if they share
    one broker symbol" — attribution lives here, one layer above the
    broker-facing `Position`/`PositionLot` aggregate, which stays a
    single per-(account, instrument) row regardless of how many
    recommendations contributed to it."""

    __tablename__ = "recommendation_attributions"
    __table_args__ = (
        sa.Index("ix_recommendation_attributions_lot", "position_lot_id"),
        sa.Index("ix_recommendation_attributions_trade", "trade_id"),
    )

    recommendation_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), index=True
    )
    mode: Mapped[RecommendationMode] = mapped_column(
        sa.Enum(RecommendationMode, name="recommendation_mode")
    )
    position_lot_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("position_lots.id"), nullable=True
    )
    trade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("trades.id"), nullable=True
    )


__all__ = [
    "ConfidenceCalibrationRecord",
    "Recommendation",
    "RecommendationAttribution",
    "RecommendationInvalidationCondition",
    "RecommendationLevel",
    "RecommendationStatusEvent",
    "RecommendationVersion",
]
