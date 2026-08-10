"""Operations bounded context — alerting, job runs, prompt governance, and
LLM call accounting (ADR-043 supersedes `models/llm_call_log.py`'s
`LLMCallLog` with `ModelCallRecord`, deliberately narrower than the
original: token/cost/latency metadata only, no full request/response
payload, per the refinement brief's "no secrets or unnecessary private
prompt content"). `models/audit_event.py`'s `AuditEvent` is unchanged and
lives in its own file, not moved here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    AgentRole,
    AlertDeliveryStatus,
    AlertSeverity,
    AlertStatus,
    AlertType,
    JobRunStatus,
    NotificationChannel,
    PromptTemplateStatus,
)


class Alert(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """Revision Prompt 11 additive columns: `alert_type` (the closed
    18-value vocabulary, `AlertType`), `expires_at` (nullable — an alert
    with no expiry is evaluated indefinitely; most types are given one
    by `services/alerts_engine.py` so a stale, no-longer-relevant alert
    doesn't sit `OPEN` forever), `dedup_key` (the identity a duplicate
    trigger is recognized against — unique only while `status=OPEN`, via
    `ix_alerts_unique_open_dedup_key` below, the same partial-unique-index
    pattern `ImportRow` (Revision Prompt 8) already established: an
    already-dismissed alert's key must be free to fire again later, a
    still-open one must not duplicate), and `evidence_type`/`evidence_id`
    (a generic polymorphic link — same pattern as
    `MorningPlanInputLink`, ADR-015 — since an alert's evidence can be
    almost any table: a `RecommendationLevel`, an `EarningsEvent`, a
    `PostEarningsConfirmationSnapshot`, a `MarketRegimeSnapshot`, etc.).
    """

    __tablename__ = "alerts"
    __table_args__ = (
        sa.Index(
            "ix_alerts_unique_open_dedup_key",
            "dedup_key",
            unique=True,
            postgresql_where=sa.text("status = 'OPEN' AND dedup_key IS NOT NULL"),
        ),
    )

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=True
    )
    alert_type: Mapped[AlertType] = mapped_column(sa.Enum(AlertType, name="alert_type"))
    severity: Mapped[AlertSeverity] = mapped_column(sa.Enum(AlertSeverity, name="alert_severity"))
    status: Mapped[AlertStatus] = mapped_column(
        sa.Enum(AlertStatus, name="alert_status"), default=AlertStatus.OPEN
    )
    title: Mapped[str] = mapped_column(sa.String(200))
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)


class AlertStatusEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only lifecycle audit trail for `Alert.status` transitions
    (principle 9, the same discipline `RecommendationStatusEvent`
    already established) — "audited" from Revision Prompt 11's own
    requirement list. Every `Alert` gets one row here at creation
    (`from_status=NULL`, `to_status=OPEN`) and one more per subsequent
    transition."""

    __tablename__ = "alert_status_events"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("alerts.id"), index=True
    )
    from_status: Mapped[AlertStatus | None] = mapped_column(
        sa.Enum(AlertStatus, name="alert_status"), nullable=True
    )
    to_status: Mapped[AlertStatus] = mapped_column(sa.Enum(AlertStatus, name="alert_status"))
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    changed_by: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)


class AlertDelivery(UUIDPkMixin, CreatedAtMixin, Base):
    """In-app only is the only channel actually used in MVP
    (BLOCKING_DECISIONS.md #9) — modeled generically so a future delivery
    channel doesn't need a schema change."""

    __tablename__ = "alert_deliveries"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("alerts.id"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        sa.Enum(NotificationChannel, name="notification_channel")
    )
    status: Mapped[AlertDeliveryStatus] = mapped_column(
        sa.Enum(AlertDeliveryStatus, name="alert_delivery_status")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class JobRun(UUIDPkMixin, CreatedAtMixin, Base):
    """Premarket/intraday/EOD scheduled-job runs (ADR-040 — in-process
    scheduler, future phase). `idempotency_key` (e.g. `"premarket:2026-08-04"`)
    prevents the same calendar day's job from double-running if the
    scheduler fires twice."""

    __tablename__ = "job_runs"

    job_name: Mapped[str] = mapped_column(sa.String(60), index=True)
    status: Mapped[JobRunStatus] = mapped_column(sa.Enum(JobRunStatus, name="job_run_status"))
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)


class PromptTemplate(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_templates"

    agent_role: Mapped[AgentRole | None] = mapped_column(
        sa.Enum(AgentRole, name="agent_role"), nullable=True
    )
    name: Mapped[str] = mapped_column(sa.String(80))


class PromptVersion(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (sa.UniqueConstraint("prompt_template_id", "version_label"),)

    prompt_template_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("prompt_templates.id"), index=True
    )
    version_label: Mapped[str] = mapped_column(sa.String(60))
    body: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[PromptTemplateStatus] = mapped_column(
        sa.Enum(PromptTemplateStatus, name="prompt_template_status")
    )


class ModelCallRecord(UUIDPkMixin, CreatedAtMixin, Base):
    """Supersedes `LLMCallLog` (ADR-043) — deliberately narrower: token
    counts, cost, latency, and a short truncated excerpt for debugging, but
    **no full request/response payload**. The shipped MVP's `LLMCallLog`
    stored the complete request/response JSON, which is exactly the
    "unnecessary private prompt content" this refinement's schema is
    explicitly told not to carry — evidence text (news headlines, etc.)
    sent to the model doesn't need to be duplicated here when it's already
    durably stored at its source (`NewsItem` etc.) and linked via
    `AgentEvidenceLink`."""

    __tablename__ = "model_call_records"

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    prompt_version_label: Mapped[str] = mapped_column(sa.String(60))
    model: Mapped[str] = mapped_column(sa.String(50))
    input_tokens: Mapped[int] = mapped_column(sa.Integer)
    output_tokens: Mapped[int] = mapped_column(sa.Integer)
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


__all__ = [
    "Alert",
    "AlertDelivery",
    "AlertStatusEvent",
    "JobRun",
    "ModelCallRecord",
    "PromptTemplate",
    "PromptVersion",
]
