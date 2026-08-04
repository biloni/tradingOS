"""Agent & committee orchestration bounded context (docs/ARCHITECTURE.md
context 5; ADR-038's execution model). Schema only this pass — no actual
Anthropic calls are wired up yet ("do not integrate external providers
yet"); `services/committee.py` (a future phase) is what would populate
these tables from real orchestration runs. The seed fixtures populate one
synthetic example of each so the read API has something real to return.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import AgentRole, AgentRunStatus, CommitteeSessionStatus


class AgentDefinition(UUIDPkMixin, CreatedAtMixin, Base):
    """One row per committee role (ADR-038's 8 roles) — the role's identity,
    independent of which prompt version is currently active for it."""

    __tablename__ = "agent_definitions"

    role: Mapped[AgentRole] = mapped_column(sa.Enum(AgentRole, name="agent_role"), unique=True)
    name: Mapped[str] = mapped_column(sa.String(80))
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class AgentVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """A specific, independently-versioned prompt+model configuration for a
    role (docs/MODEL_GOVERNANCE.md's "per-role prompt/model versions" —
    changing the Bear Analyst's prompt doesn't re-version the other 7)."""

    __tablename__ = "agent_versions"
    __table_args__ = (sa.UniqueConstraint("agent_definition_id", "version_label"),)

    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("agent_definitions.id"), index=True
    )
    version_label: Mapped[str] = mapped_column(sa.String(60))
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(sa.String(60))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class CommitteeSession(UUIDPkMixin, CreatedAtMixin, Base):
    """One full committee run for one instrument (ADR-038: 5 parallel
    analysts, then Risk/PM, then CIO — each an `AgentRun` under this
    session). `triggered_by` names what caused the run (e.g.
    `PREMARKET_JOB`, `MANUAL`) without needing a full job-run FK for every
    trigger source."""

    __tablename__ = "committee_sessions"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    triggered_by: Mapped[str] = mapped_column(sa.String(40))
    status: Mapped[CommitteeSessionStatus] = mapped_column(
        sa.Enum(CommitteeSessionStatus, name="committee_session_status")
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class AgentRun(UUIDPkMixin, CreatedAtMixin, Base):
    """One role's single call within a committee session.
    `input_snapshot`/`output_snapshot` are the exact evidence bundle and
    structured response — principle 9's audit trail applied to the
    committee, and the concrete data NFR-04 (auditability) needs to
    reconstruct a past committee run without re-querying any vendor."""

    __tablename__ = "agent_runs"

    committee_session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("committee_sessions.id"), index=True
    )
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("agent_versions.id")
    )
    status: Mapped[AgentRunStatus] = mapped_column(sa.Enum(AgentRunStatus, name="agent_run_status"))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(PORTABLE_JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # The other direction (which model call(s) this run produced) is on
    # `ModelCallRecord.agent_run_id` instead — avoids a circular FK between
    # the two tables, and naturally allows a run to have produced more than
    # one call record (e.g. one retry after a malformed structured output,
    # docs/MODEL_GOVERNANCE.md).


class AgentEvidenceLink(UUIDPkMixin, CreatedAtMixin, Base):
    """Which specific evidence rows a given agent run actually cited
    (FR-17: Bull/Bear must cite specific evidence, not just assert a view).
    Generic `evidence_type` + `evidence_id` (same reasoning as
    `AuditEvent.ref_id`, ADR-015) since evidence spans many different
    tables (news items, fundamentals snapshots, indicator snapshots, ...)
    that a single FK column can't target."""

    __tablename__ = "agent_evidence_links"
    __table_args__ = (sa.Index("ix_agent_evidence_links_lookup", "agent_run_id", "evidence_type"),)

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("agent_runs.id")
    )
    evidence_type: Mapped[str] = mapped_column(sa.String(50))
    evidence_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True))


class AgentOpinion(UUIDPkMixin, CreatedAtMixin, Base):
    """The role's own structured verdict, split out from `AgentRun.output_snapshot`
    for queryability (e.g. "show me every BEARISH opinion this week")
    without parsing JSON. One-to-one with `AgentRun` (a run either produced
    a valid opinion or it didn't — a failed run has no row here)."""

    __tablename__ = "agent_opinions"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("agent_runs.id"), unique=True
    )
    stance: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    structured_output: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)


__all__ = [
    "AgentDefinition",
    "AgentEvidenceLink",
    "AgentOpinion",
    "AgentRun",
    "AgentVersion",
    "CommitteeSession",
]
