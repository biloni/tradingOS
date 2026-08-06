"""Morning plan bounded context (Revision Prompt R3, additive to Phase
8/ADR-050) — implements docs/MORNING_PLAN_SPEC.md and ADR-047's
scheduler-owned job-lineage design. `MorningPlanRun` is one scheduler
invocation; it can produce more than one `MorningPlanVersion` (a
`PRELIMINARY` at 05:45 and a `FINAL` at 06:10 are two separate,
separately-stored, immutable artifacts) — a rerun always creates a new
version row, never overwrites an existing one (R3's explicit test
requirement).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    AlertDeliveryStatus,
    DeliveryChannel,
    MorningPlanRunStatus,
    MorningPlanSectionKey,
    MorningPlanVersionLabel,
    PlanCompletenessStatus,
)


class MorningPlanRun(UUIDPkMixin, CreatedAtMixin, Base):
    """One scheduler invocation (ADR-047). `idempotency_key` (e.g.
    `"morning-plan:2026-08-06:FINAL"`) prevents the same scheduled slot
    from double-running if the scheduler fires twice — the same pattern
    `job_runs.idempotency_key` already established in Phase 8."""

    __tablename__ = "morning_plan_runs"

    job_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("job_runs.id"), nullable=True
    )
    plan_date: Mapped[date] = mapped_column(sa.Date, index=True)
    triggered_by: Mapped[str] = mapped_column(sa.String(40))
    status: Mapped[MorningPlanRunStatus] = mapped_column(
        sa.Enum(MorningPlanRunStatus, name="morning_plan_run_status")
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class MorningPlanVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Immutable once published — a `PRELIMINARY`/`FINAL`/`AD_HOC`/
    `CORRECTION` artifact for one `plan_date`. Never edited in place;
    a rerun or correction is always a new row (R3 test requirement:
    "plan reruns create versions rather than overwrite")."""

    __tablename__ = "morning_plan_versions"
    __table_args__ = (sa.Index("ix_morning_plan_versions_dashboard", "plan_date", "version_label"),)

    morning_plan_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_runs.id"), index=True
    )
    plan_date: Mapped[date] = mapped_column(sa.Date)
    version_label: Mapped[MorningPlanVersionLabel] = mapped_column(
        sa.Enum(MorningPlanVersionLabel, name="morning_plan_version_label")
    )
    version_number: Mapped[int] = mapped_column(sa.Integer)
    evidence_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    completeness_status: Mapped[PlanCompletenessStatus] = mapped_column(
        sa.Enum(PlanCompletenessStatus, name="plan_completeness_status")
    )


class MorningPlanInputLink(UUIDPkMixin, CreatedAtMixin, Base):
    """The lineage manifest (ADR-047) — which evidence/recommendation/
    regime rows a given plan version was built from, recorded generically
    (`input_type` + `input_id`, the same "record_type + ref_id" reasoning
    as `audit_events.ref_id`, ADR-015) since the referenced rows span many
    different tables."""

    __tablename__ = "morning_plan_input_links"
    __table_args__ = (
        sa.Index("ix_morning_plan_input_links_lookup", "morning_plan_version_id", "input_type"),
    )

    morning_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_versions.id")
    )
    input_type: Mapped[str] = mapped_column(sa.String(50))
    input_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True))


class MorningPlanSection(UUIDPkMixin, CreatedAtMixin, Base):
    """The fixed seven-section grouping (R0 MDS-5), in `display_order`."""

    __tablename__ = "morning_plan_sections"
    __table_args__ = (sa.UniqueConstraint("morning_plan_version_id", "section_key"),)

    morning_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_versions.id"), index=True
    )
    section_key: Mapped[MorningPlanSectionKey] = mapped_column(
        sa.Enum(MorningPlanSectionKey, name="morning_plan_section_key")
    )
    display_order: Mapped[int] = mapped_column(sa.Integer)


class MorningPlanItem(UUIDPkMixin, CreatedAtMixin, Base):
    """One card within one section. `recommendation_version_id` is
    nullable so a Data Problems item (naming what failed, not a
    recommendation) is representable too."""

    __tablename__ = "morning_plan_items"

    morning_plan_section_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_sections.id"), index=True
    )
    recommendation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), nullable=True
    )
    display_order: Mapped[int] = mapped_column(sa.Integer)
    headline: Mapped[str] = mapped_column(sa.String(200))


class MorningPlanQualityCheck(UUIDPkMixin, CreatedAtMixin, Base):
    """Per-check detail behind a version's `completeness_status`
    (docs/MORNING_PLAN_SPEC.md's "what data is required before COMPLETE")
    — append-only, one row per named check per version."""

    __tablename__ = "morning_plan_quality_checks"

    morning_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_versions.id"), index=True
    )
    check_name: Mapped[str] = mapped_column(sa.String(60))
    passed: Mapped[bool] = mapped_column(sa.Boolean)
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class MorningPlanDeliveryEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only delivery log. `channel=COWORK` rows only ever exist for
    a `FINAL` version already published (ADR-049) — enforced at the
    service layer, not by this table's own schema, since "published
    already" is a fact about `MorningPlanVersion`'s existence/timing, not
    something a column constraint here can see."""

    __tablename__ = "morning_plan_delivery_events"

    morning_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("morning_plan_versions.id"), index=True
    )
    channel: Mapped[DeliveryChannel] = mapped_column(
        sa.Enum(DeliveryChannel, name="delivery_channel")
    )
    status: Mapped[AlertDeliveryStatus] = mapped_column(
        sa.Enum(AlertDeliveryStatus, name="alert_delivery_status")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


__all__ = [
    "MorningPlanDeliveryEvent",
    "MorningPlanInputLink",
    "MorningPlanItem",
    "MorningPlanQualityCheck",
    "MorningPlanRun",
    "MorningPlanSection",
    "MorningPlanVersion",
]
