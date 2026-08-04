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
    JobRunStatus,
    NotificationChannel,
    PromptTemplateStatus,
)


class Alert(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=True
    )
    severity: Mapped[AlertSeverity] = mapped_column(sa.Enum(AlertSeverity, name="alert_severity"))
    status: Mapped[AlertStatus] = mapped_column(
        sa.Enum(AlertStatus, name="alert_status"), default=AlertStatus.OPEN
    )
    title: Mapped[str] = mapped_column(sa.String(200))
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


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
    "JobRun",
    "ModelCallRecord",
    "PromptTemplate",
    "PromptVersion",
]
