"""Outcomes & learning bounded context (ADR-043 supersedes
`models/strategy_version.py`'s standalone `StrategyVersion` with a
`StrategyDefinition` parent + `StrategyVersion` child, mirroring
`AgentDefinition`/`AgentVersion`'s shape for the same reason: a definition
is a stable identity, a version is one governed, backtested, approved
configuration of it).
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
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    ModelChangeProposalStatus,
    RecommendationOutcomeClassification,
    StrategyFamily,
    StrategyVersionStatus,
    TradeReviewRating,
)


class RecommendationOutcome(UUIDPkMixin, TimestampMixin, Base):
    """ADR-041 — computed (never self-reported) classification of what the
    user actually did about a recommendation, plus its eventual result
    once the linked trade closes. One row per `Recommendation` (not per
    version — the outcome is about the call as a whole)."""

    __tablename__ = "recommendation_outcomes"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), unique=True
    )
    classification: Mapped[RecommendationOutcomeClassification] = mapped_column(
        sa.Enum(RecommendationOutcomeClassification, name="recommendation_outcome_classification")
    )
    linked_trade_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("trades.id"), nullable=True
    )
    matched_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class HypotheticalTradeOutcome(UUIDPkMixin, CreatedAtMixin, Base):
    """ "What would have happened" for an `IGNORED` recommendation — lets
    the performance dashboard show the cost of inaction, not just realized
    results. Simulated, clearly labeled as such (never conflated with a
    real `Trade`)."""

    __tablename__ = "hypothetical_trade_outcomes"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), index=True
    )
    simulated_entry_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    simulated_exit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    simulated_exit_reason: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    simulated_pnl_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class TradeReview(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "trade_reviews"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("trades.id"), index=True
    )
    rating: Mapped[TradeReviewRating | None] = mapped_column(
        sa.Enum(TradeReviewRating, name="trade_review_rating"), nullable=True
    )
    review_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class PerformanceSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (sa.UniqueConstraint("account_id", "period_start", "period_end"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    period_start: Mapped[date] = mapped_column(sa.Date)
    period_end: Mapped[date] = mapped_column(sa.Date)
    realized_pnl: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    win_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    avg_r_multiple: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)


class BenchmarkSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "benchmark_snapshots"
    __table_args__ = (sa.UniqueConstraint("benchmark_ticker", "period_start", "period_end"),)

    benchmark_ticker: Mapped[str] = mapped_column(sa.String(10))
    period_start: Mapped[date] = mapped_column(sa.Date)
    period_end: Mapped[date] = mapped_column(sa.Date)
    return_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4))


class StrategyDefinition(UUIDPkMixin, OwnedMixin, CreatedAtMixin, Base):
    """`family` (Revision Prompt R3, additive, nullable) classifies which
    decision workflow this strategy governs — `INVESTMENT_QUALITY`,
    `EARNINGS_PRE_EVENT`, `EARNINGS_POST_CONFIRMATION`, or `GENERIC` for
    anything not yet categorized (including every Phase 1-7/8 strategy
    definition already in the database, which this revision's migration
    backfills to `GENERIC` rather than leaving NULL)."""

    __tablename__ = "strategy_definitions"

    name: Mapped[str] = mapped_column(sa.String(80))
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    family: Mapped[StrategyFamily] = mapped_column(
        sa.Enum(StrategyFamily, name="strategy_family"), default=StrategyFamily.GENERIC
    )


class StrategyVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Unchanged governance mechanism from the shipped MVP (ADR-026/027/028,
    principle 16) — now a version under a `StrategyDefinition` parent
    rather than a standalone table (ADR-043)."""

    __tablename__ = "strategy_versions"

    strategy_definition_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("strategy_definitions.id"), index=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    status: Mapped[StrategyVersionStatus] = mapped_column(
        sa.Enum(StrategyVersionStatus, name="strategy_version_status")
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ScoringWeightVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """A queryable projection of the per-signal weights that live inside
    `StrategyVersion.config` (JSON) — `services/scoring.py` continues to
    read the JSON as its source of truth; this table exists so "show me
    how the trend weight has changed across versions" is a normal query
    instead of a JSON-path extraction."""

    __tablename__ = "scoring_weight_versions"
    __table_args__ = (sa.UniqueConstraint("strategy_version_id", "signal_name"),)

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("strategy_versions.id"), index=True
    )
    signal_name: Mapped[str] = mapped_column(sa.String(30))
    weight: Mapped[Decimal] = mapped_column(sa.Numeric(8, 4))


class ModelChangeProposal(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """Principle 16 generalized beyond scoring weights (FR-46) — a change
    to an agent's prompt version, the committee pre-filter bar, or any
    other governed config that isn't a `StrategyVersion` itself routes
    through this instead. `subject_ref_id` is a generic UUID (same
    `record_type`-style reasoning as `AuditEvent.ref_id`, ADR-015) since
    the subject can be several different entity types.

    Revision Prompt 14 additive columns: `evidence_package` is the one
    JSON home for every structured artifact the prompt's own requirement
    list names (evidence + sample size, current/proposed version
    snapshots, economic rationale, train/validation/out-of-sample/walk-
    forward results, sensitivity, costs, operational risks, rollback
    plan) — a rich, self-describing blob rather than a dozen narrow
    columns, matching this project's existing convention for this kind
    of structured artifact (`EventBacktestRun.config`/`results_summary`,
    `StrategyVersion.config`). `activated_at`/`activated_by`/
    `rolled_back_at`/`rolled_back_by`/`rollback_reason` record the two
    state transitions this revision adds — see
    `models/enums.py::MODEL_CHANGE_PROPOSAL_TRANSITIONS`."""

    __tablename__ = "model_change_proposals"

    subject_type: Mapped[str] = mapped_column(sa.String(50))
    subject_ref_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[ModelChangeProposalStatus] = mapped_column(
        sa.Enum(ModelChangeProposalStatus, name="model_change_proposal_status")
    )
    proposed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    evidence_package: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)
    activated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    activated_by: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    rolled_back_by: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ModelChangeApproval(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "model_change_approvals"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("model_change_proposals.id"), index=True
    )
    decision: Mapped[ModelChangeProposalStatus] = mapped_column(
        sa.Enum(ModelChangeProposalStatus, name="model_change_proposal_status")
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class StrategyEligibilitySnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """Whether a given instrument currently qualifies for a strategy
    version's own eligibility rule (e.g. a liquidity floor, a sector
    exclusion) — append-only, one row per evaluation, so "why wasn't this
    name considered" is answerable from stored data."""

    __tablename__ = "strategy_eligibility_snapshots"
    __table_args__ = (
        sa.Index("ix_strategy_eligibility_snapshots_lookup", "strategy_version_id", "as_of"),
    )

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("strategy_versions.id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    eligible: Mapped[bool] = mapped_column(sa.Boolean)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class DecisionPolicyVersion(UUIDPkMixin, OwnedMixin, CreatedAtMixin, Base):
    """A versioned, governed configuration distinct from `StrategyVersion`
    (which holds scoring weights) — e.g. the committee pre-filter bar, the
    hybrid-earnings AND-gate's specific thresholds, or the Morning
    Decision Plan's `INCOMPLETE`-labeling percentage. Same
    propose-> review -> approve/reject governance mechanism as
    `StrategyVersion` (principle 16, FR-45/46 — a decision-policy change
    is a strategy change like any other), reused rather than duplicated."""

    __tablename__ = "decision_policy_versions"

    version_label: Mapped[str] = mapped_column(sa.String(60))
    config: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    status: Mapped[StrategyVersionStatus] = mapped_column(
        sa.Enum(StrategyVersionStatus, name="strategy_version_status")
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


__all__ = [
    "BenchmarkSnapshot",
    "DecisionPolicyVersion",
    "HypotheticalTradeOutcome",
    "ModelChangeApproval",
    "ModelChangeProposal",
    "PerformanceSnapshot",
    "RecommendationOutcome",
    "ScoringWeightVersion",
    "StrategyDefinition",
    "StrategyEligibilitySnapshot",
    "StrategyVersion",
    "TradeReview",
]
