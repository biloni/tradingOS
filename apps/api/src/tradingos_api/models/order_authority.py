"""Order authority bounded context (Revision Prompt R3, additive to
Phase 8/ADR-050) — the schema-backed proposal -> policy evaluation ->
approval lifecycle docs/ORDER_AUTHORITY_MODEL.md defines, upstream of
and distinct from the existing `Order`/`Execution` tables (Phase 8),
which begin only once an approval is bound and (for paper accounts)
submitted. **No table here is ever written by a live broker call, in
this revision or Revision Prompt 10** — "do not add a live broker
submission endpoint yet" remains true; Revision Prompt 10 only wires
real **paper** submission (`services/order_execution.py`, the single
broker-boundary entry point).

Revision Prompt 10 additive columns: `ApprovalBoundFields.quote_price_at_approval`
(the concrete price snapshot the "price moved" invalidation check
compares a fresh quote against — the architecture doc's own "moved a
configurable percentage from the approval's snapshot price" question 5,
previously only a timestamp with no comparable value);
`BrokerSubmissionAttempt.resulting_order_id`/`request_snapshot`/
`response_snapshot` (linking one submission attempt to the real `Order`
it produced, plus a redacted request/response record for audit without
ever storing a credential); `OrderApproval.auto_policy_version_id`
(which `PaperAutoPolicyVersion` authorized an automatic submission, when
there was one). New tables: `PaperAutoPolicyVersion` (the
`PAPER_AUTO_POLICY` grant `policy.order_authority.AutoPolicyGrant`
requires — disabled by default, versioned, append-only) and
`CancelOpenOrdersEvent` (OA-9's second, independent control, alongside
the pre-existing `ExecutionKillSwitchEvent`).

This is deliberately a separate model module from
`tradingos_api.policy.order_authority` (R0): that module is pure,
DB-agnostic Python (`OrderAuthorityMode`, `assert_order_authorized()`)
with no SQLAlchemy dependency; this module is the persistence layer that
records the *outcome* of calling it. Neither imports the other.
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
from tradingos_api.models.enums import (
    ApprovalInvalidationReason,
    BrokerSubmissionOutcome,
    EnvironmentLabel,
    KillSwitchBehavior,
    OrderApprovalStatus,
    OrderAuthorityMode,
    OrderProposalStatus,
    OrderSide,
    OrderType,
    RecommendationMode,
    TimeInForce,
)


class OperatingModeHistory(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only log of every operating-mode change — today's
    `GET /api/v1/settings/operating-mode` (R2) reads a config value with
    no history; this table is where a future write path
    (`PATCH`-equivalent, not built this pass) would log to, and where the
    kill switch's forced transition to `RESEARCH_ONLY` (OA-9) is
    recorded."""

    __tablename__ = "operating_mode_history"

    mode: Mapped[OrderAuthorityMode] = mapped_column(
        sa.Enum(OrderAuthorityMode, name="order_authority_mode")
    )
    changed_by: Mapped[str] = mapped_column(sa.String(80))
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class OrderProposal(UUIDPkMixin, TimestampMixin, Base):
    """The stable identity — "a recommendation wants to become an order."
    `status` is the *current* lifecycle state (`ORDER_PROPOSAL_TRANSITIONS`);
    the actual proposed terms (quantity, prices) live on the latest
    `OrderProposalVersion`, mirroring `Recommendation`/`RecommendationVersion`'s
    split. `updated_at` (`TimestampMixin`) is the optimistic-concurrency
    token a future PATCH-style endpoint compares `expected_updated_at`
    against, the same pattern `watchlist_items`/`alerts` already use."""

    __tablename__ = "order_proposals"
    __table_args__ = (sa.Index("ix_order_proposals_status", "status"),)

    recommendation_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    mode: Mapped[RecommendationMode] = mapped_column(
        sa.Enum(RecommendationMode, name="recommendation_mode")
    )
    side: Mapped[OrderSide] = mapped_column(sa.Enum(OrderSide, name="order_side"))
    status: Mapped[OrderProposalStatus] = mapped_column(
        sa.Enum(OrderProposalStatus, name="order_proposal_status"),
        default=OrderProposalStatus.DRAFT,
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)


class OrderProposalVersion(UUIDPkMixin, CreatedAtMixin, Base):
    """Immutable once written — revising a proposal's terms creates the
    next version, never edits a prior one (the same discipline as
    `RecommendationVersion`).

    Revision Prompt 7 additive columns fill out its "ORDER PROPOSAL
    FIELDS" list that R3's original columns above didn't yet carry:
    `environment` (account/environment, alongside `OrderProposal.account_id`),
    `outside_hours` (R3 only captured this at `ApprovalBoundFields`,
    post-approval; a proposal states its own intent before that),
    `attached_legs` (the OCO/bracket relationship, mirroring
    `ApprovalBoundFields.attached_legs`'s shape one stage earlier),
    `max_slippage_bps`, `valid_from`/`expires_at` (this proposal's own
    validity window — distinct from `OrderApproval.expires_at`, which is
    the *approval*'s separate, later expiry), `risk_policy_version`
    (which `RiskPolicyVersion` the sizing math was computed against),
    `data_cutoff`/`quote_observed_at` (point-in-time provenance for the
    price/evidence this proposal's numbers came from), and
    `requires_approval` (this proposal's own computed answer to "does
    this need a human click," from the operating mode in force at
    proposal time — never recomputed silently later)."""

    __tablename__ = "order_proposal_versions"
    __table_args__ = (sa.UniqueConstraint("order_proposal_id", "version_number"),)

    order_proposal_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_proposals.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(sa.Integer)
    order_type: Mapped[OrderType] = mapped_column(sa.Enum(OrderType, name="order_type"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    limit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    time_in_force: Mapped[TimeInForce] = mapped_column(
        sa.Enum(TimeInForce, name="time_in_force"), default=TimeInForce.DAY
    )
    max_notional: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    rationale: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    environment: Mapped[EnvironmentLabel | None] = mapped_column(
        sa.Enum(EnvironmentLabel, name="environment_label"), nullable=True
    )
    outside_hours: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    attached_legs: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)
    max_slippage_bps: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 4), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    risk_policy_version: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    data_cutoff: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    quote_observed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    requires_approval: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class OrderPolicyEvaluation(UUIDPkMixin, CreatedAtMixin, Base):
    """One recorded call to the order-authority policy gate
    (`policy.order_authority.assert_order_authorized()`, R0) for one
    proposal version — append-only, so "was this ever authorized, under
    which mode, and if not, why" is always answerable from stored data
    (principle 9), without re-deriving it from whatever the live config
    says today."""

    __tablename__ = "order_policy_evaluations"

    order_proposal_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_proposal_versions.id"), index=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    requested_mode: Mapped[OrderAuthorityMode] = mapped_column(
        sa.Enum(OrderAuthorityMode, name="order_authority_mode")
    )
    authorized: Mapped[bool] = mapped_column(sa.Boolean)
    denial_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class OrderApproval(UUIDPkMixin, TimestampMixin, Base):
    """The approval record (ADR-048). `integrity_hash` is a SHA-256 hex
    digest over the exact `ApprovalBoundFields` row created alongside it
    — `services/order_authority.py` (future) recomputes and compares this
    hash before ever allowing a submission, so a bound field changing
    after the fact is detectable without a live diff against a mutable
    `Order` row. `expires_at` plus `OrderApprovalStatus`'s one-way
    `APPROVED -> {INVALIDATED}` transition (never back to `APPROVED` from
    `EXPIRED`/`INVALIDATED`) is what R3's "expired approval cannot return
    an approved state" test proves. `updated_at` (`TimestampMixin`) is
    this row's own optimistic-concurrency token."""

    __tablename__ = "order_approvals"
    __table_args__ = (sa.Index("ix_order_approvals_status", "status"),)

    order_proposal_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_proposal_versions.id"), index=True
    )
    approved_by: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[OrderApprovalStatus] = mapped_column(
        sa.Enum(OrderApprovalStatus, name="order_approval_status"),
        default=OrderApprovalStatus.PENDING,
    )
    integrity_hash: Mapped[str] = mapped_column(sa.String(64))
    auto_policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("paper_auto_policy_versions.id"), nullable=True
    )


class ApprovalBoundFields(UUIDPkMixin, CreatedAtMixin, Base):
    """Immutable snapshot of exactly what OA-8 requires an approval to
    bind: account, symbol, side, quantity, order type, limit/stop prices,
    time in force, outside-hours flag, attached legs, maximum notional,
    and the recommendation version — captured once, at approval time,
    never edited (ADR-048). `integrity_hash` on the parent `OrderApproval`
    is computed over this row's fields in a fixed, documented order (see
    `services/order_authority.py::compute_bound_fields_hash()`)."""

    __tablename__ = "approval_bound_fields"

    order_approval_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_approvals.id"), unique=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    side: Mapped[OrderSide] = mapped_column(sa.Enum(OrderSide, name="order_side"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    order_type: Mapped[OrderType] = mapped_column(sa.Enum(OrderType, name="order_type"))
    limit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    time_in_force: Mapped[TimeInForce] = mapped_column(sa.Enum(TimeInForce, name="time_in_force"))
    outside_hours: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    attached_legs: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)
    max_notional: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    recommendation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), nullable=True
    )
    quote_price_at_approval: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(18, 6), nullable=True
    )


class ApprovalInvalidation(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only. Distinct from a rejection: an invalidation is the
    system unilaterally refusing to honor an otherwise-still-pending or
    already-approved approval (price moved, confirmation went stale,
    identity became ambiguous, kill switch fired, or a bound field
    changed) — docs/ORDER_AUTHORITY_MODEL.md."""

    __tablename__ = "approval_invalidations"

    order_approval_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_approvals.id"), index=True
    )
    reason: Mapped[ApprovalInvalidationReason] = mapped_column(
        sa.Enum(ApprovalInvalidationReason, name="approval_invalidation_reason")
    )
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    invalidated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class BrokerSubmissionAttempt(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only. Through R3/Revision Prompt 9, every row ever written
    had `outcome` in `{NOT_ATTEMPTED, DENIED}` and `environment_label` in
    `{RESEARCH, PAPER}` — no code path could write `SUCCEEDED` at all.
    Revision Prompt 10 is what actually reaches a real (paper-only)
    broker: `SUCCEEDED`/`FAILED`/`TIMEOUT_UNKNOWN` become real, live
    outcomes for `environment_label=PAPER`; `environment_label=LIVE`
    remains impossible to reach `SUCCEEDED` for by construction — no
    code path in `services/order_execution.py` ever sets `is_live=True`
    (see that module's docstring). `idempotency_key` is this **attempt's**
    own local dedup key (`f"order-approval:{approval_id}:attempt{n}"`,
    the same numbered-attempt pattern `services/morning_plan_scheduler.py`
    already established) — distinct from the *broker-facing*
    `client_order_id` (`services/order_execution.py::_client_order_id()`,
    derived on demand, never stored as its own column since it is a pure
    function of `order_approval_id` alone) that stays stable **across**
    every attempt for the same approval, which is what lets a real broker
    safely reject/de-duplicate a second submit if the first one actually
    succeeded despite an ambiguous local timeout.
    `resulting_order_id`/`request_snapshot`/`response_snapshot` are
    Revision Prompt 10's additions: which real `Order` row this attempt
    produced (nullable — a `FAILED`/`DENIED`/`TIMEOUT_UNKNOWN` attempt
    produced none), and a **redacted** record of what was sent/received
    (`services/order_execution.py::_redact_broker_payload()` is the one
    place redaction rules live — no API key, secret, or full account
    number is ever written into either snapshot)."""

    __tablename__ = "broker_submission_attempts"

    order_approval_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("order_approvals.id"), index=True
    )
    attempted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    environment_label: Mapped[EnvironmentLabel] = mapped_column(
        sa.Enum(EnvironmentLabel, name="environment_label")
    )
    outcome: Mapped[BrokerSubmissionOutcome] = mapped_column(
        sa.Enum(BrokerSubmissionOutcome, name="broker_submission_outcome")
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    resulting_order_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True
    )
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)


class ExecutionKillSwitchEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only (OA-9) — every kill-switch activation/deactivation is
    its own audited row, independent of `ApprovalInvalidation` (a kill
    switch firing writes both: one `ExecutionKillSwitchEvent` for the
    switch itself, and one `ApprovalInvalidation` per approval it
    invalidated)."""

    __tablename__ = "execution_kill_switch_events"

    activated_by: Mapped[str] = mapped_column(sa.String(80))
    activated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class BrokerEnvironmentAttestation(UUIDPkMixin, CreatedAtMixin, Base):
    """The recorded `(environment, account, broker_endpoint)` triple OA-6
    requires be unambiguous before any live action — append-only, so a
    future ambiguity check has a real record to compare a proposed
    submission's identity against, rather than an ad hoc parameter with
    nothing to validate it came from."""

    __tablename__ = "broker_environment_attestations"

    environment_label: Mapped[EnvironmentLabel] = mapped_column(
        sa.Enum(EnvironmentLabel, name="environment_label")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True
    )
    broker_endpoint: Mapped[str] = mapped_column(sa.String(200))
    attested_by: Mapped[str] = mapped_column(sa.String(80))
    attested_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class PaperAutoPolicyVersion(UUIDPkMixin, OwnedMixin, CreatedAtMixin, Base):
    """The explicitly-enabled, versioned automation grant
    `policy.order_authority.AutoPolicyGrant`/OA-4 requires before
    `PAPER_AUTO_POLICY` may submit anything without a per-order human
    click (Revision Prompt 10). Append-only, mirroring `RiskPolicyVersion`/
    `StrategyVersion`'s pattern — changing any field creates the next
    `version_number`, it never edits a live row a currently-running
    auto-submission might be mid-read of. **Disabled by default**: no row
    at all (never having been configured) and a row with `enabled=False`
    both mean "not authorized," identically to `AutoPolicyGrant(enabled=False, ...)`.
    `services/paper_auto_policy.py` is the one place these fields are
    evaluated; a policy can only ever narrow what the deterministic hard
    vetoes (`services/hard_vetoes.py`) already allow, never widen it —
    "auto-policy can never override a hard risk or data-quality gate" is
    enforced by construction (the auto-policy check runs *in addition
    to*, never *instead of*, `evaluate_hard_vetoes()`)."""

    __tablename__ = "paper_auto_policy_versions"
    __table_args__ = (sa.UniqueConstraint("owner_user_id", "version_number"),)

    version_number: Mapped[int] = mapped_column(sa.Integer)
    enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    eligible_strategy_families: Mapped[list[str]] = mapped_column(PORTABLE_JSON, default=list)
    min_score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 2), default=Decimal(6))
    max_orders_per_day: Mapped[int] = mapped_column(sa.Integer, default=1)
    max_daily_notional: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    max_per_order_risk_pct: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    allowed_time_windows: Mapped[list[dict[str, Any]]] = mapped_column(PORTABLE_JSON, default=list)
    allowed_order_types: Mapped[list[str]] = mapped_column(PORTABLE_JSON, default=list)
    kill_switch_behavior: Mapped[KillSwitchBehavior] = mapped_column(
        sa.Enum(KillSwitchBehavior, name="kill_switch_behavior"),
        default=KillSwitchBehavior.HALT_AND_CANCEL_OPEN,
    )
    created_by: Mapped[str] = mapped_column(sa.String(80))


class CancelOpenOrdersEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """OA-9's second, independent control — "a separate action that
    cancels every open order still at the broker, independent of the
    kill switch." Append-only, its own audited row distinct from
    `ExecutionKillSwitchEvent` (a user may want to stop new entries
    without touching existing open orders, or vice versa). `account_id`
    NULL means "every account," matching this being a single-user,
    small-account-count system where an unscoped cancel-all is itself a
    meaningful, auditable action, not an oversight."""

    __tablename__ = "cancel_open_orders_events"

    account_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True
    )
    triggered_by: Mapped[str] = mapped_column(sa.String(80))
    triggered_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    orders_canceled_count: Mapped[int] = mapped_column(sa.Integer, default=0)


__all__ = [
    "ApprovalBoundFields",
    "ApprovalInvalidation",
    "BrokerEnvironmentAttestation",
    "BrokerSubmissionAttempt",
    "CancelOpenOrdersEvent",
    "ExecutionKillSwitchEvent",
    "OperatingModeHistory",
    "OrderApproval",
    "OrderPolicyEvaluation",
    "OrderProposal",
    "OrderProposalVersion",
    "PaperAutoPolicyVersion",
]
