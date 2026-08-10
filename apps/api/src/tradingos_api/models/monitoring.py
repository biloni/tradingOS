"""Active-position monitoring and post-earnings confirmation workflow
state (Revision Prompt 11). Deliberately a new, small module rather than
folding into `models/market_evidence.py` (evidence, never workflow
state) or `models/recommendations.py` (the recommendation identity
itself, not the process that produces one).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import PostEarningsWorkflowStatus


class PostEarningsWorkflowRun(UUIDPkMixin, TimestampMixin, Base):
    """One row per (earnings_event, instrument, account) — the POST-
    EARNINGS WORKFLOW's own state, mutated in place across its 10 steps
    (`TimestampMixin`, not append-only: this is a live process, not a
    fact log — the process's own history is instead reconstructable from
    the `Recommendation`/`RecommendationVersion`/`Alert` rows it produces
    along the way, each of which is its own immutable record).

    `idempotency_key` (`f"post-earnings:{earnings_event_id}:{instrument_id}:{account_id}"`)
    is enforced unique — "duplicate release" detection: re-running the
    workflow for an event/instrument/account already tracked returns the
    existing row rather than starting a second, parallel one.

    `pre_event_recommendation_id`/`post_event_recommendation_id` are two
    separate, independently-nullable columns — never one column reused
    — implementing "the pre-event trade and post-confirmation trade
    retain separate recommendation versions and outcomes" as a schema
    fact, not a documentation promise."""

    __tablename__ = "post_earnings_workflow_runs"

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    pre_event_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), nullable=True
    )
    post_event_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), nullable=True
    )
    status: Mapped[PostEarningsWorkflowStatus] = mapped_column(
        sa.Enum(PostEarningsWorkflowStatus, name="post_earnings_workflow_status"),
        default=PostEarningsWorkflowStatus.WAITING_FOR_DATA,
    )
    results_ingested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    confirmation_window_ends_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    reversal_detected: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(150), unique=True)
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


__all__ = ["PostEarningsWorkflowRun"]
