"""Approval-integrity and expiration logic for `OrderApproval`/
`ApprovalBoundFields` (ADR-048, Revision Prompt R3), plus Revision
Prompt 10's order-authority safety layer: the kill switch (OA-9), the
paper-only broker-boundary fail-closed check (OA-6), and the
price-move-invalidation threshold (architecture question 5).

`compute_bound_fields_hash()` is the one place the fixed field order and
serialization rules for `ApprovalBoundFields`.`integrity_hash` are
defined — `models.order_authority.ApprovalBoundFields`'s own docstring
points here. `assert_can_transition_to_approved()` is the combined guard
("expired approval cannot return an approved state") that a future
approval-decision endpoint must call: it is not enough that the DB
transition map forbids `EXPIRED -> APPROVED`, because `expires_at` can
pass *before* anything has written `EXPIRED` to the row — this function
treats a past `expires_at` as an immediate, unconditional denial
regardless of what `status` currently says.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    ORDER_APPROVAL_TRANSITIONS,
    AccountType,
    ApprovalInvalidationReason,
    EnvironmentLabel,
    OrderApprovalStatus,
)
from tradingos_api.models.order_authority import (
    ApprovalInvalidation,
    ExecutionKillSwitchEvent,
    OrderApproval,
)
from tradingos_api.policy.order_authority import OrderAuthorityDenied, OrderAuthorityMode
from tradingos_api.services.lifecycle import assert_transition_allowed

# Architecture question 5's own answer is "the stop distance's own
# ATR-derived width" — not implemented here; wiring a per-symbol ATR
# into this check is a documented future refinement (docs/DECISIONS.md).
# This flat default is the versioned, configurable placeholder in the
# meantime — a real percentage move, not "vibes," and every invalidation
# it produces is recorded with the move that triggered it.
DEFAULT_PRICE_MOVE_THRESHOLD_PCT = Decimal("1.0")


@dataclass(frozen=True)
class BoundFieldsSnapshot:
    """The exact set of `ApprovalBoundFields` columns the integrity hash
    covers, in the fixed order `compute_bound_fields_hash()` hashes them
    in. Changing this order is itself a breaking change to every
    previously-computed hash — don't reorder without a migration note."""

    account_id: uuid.UUID
    instrument_id: uuid.UUID
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    stop_price: Decimal | None
    time_in_force: str
    outside_hours: bool
    attached_legs: dict[str, Any]
    max_notional: Decimal | None
    recommendation_version_id: uuid.UUID | None


def compute_bound_fields_hash(fields: BoundFieldsSnapshot) -> str:
    """SHA-256 hex digest over `fields`, in a fixed field order with a
    deterministic serialization per type (UUIDs and enums as their
    string value, `Decimal`/`None` via `str()`, `attached_legs` via
    `json.dumps(..., sort_keys=True)`). Two `BoundFieldsSnapshot`s with
    identical field values always hash identically; any single field
    changing changes the digest."""
    parts = [
        str(fields.account_id),
        str(fields.instrument_id),
        fields.side,
        str(fields.quantity),
        fields.order_type,
        str(fields.limit_price),
        str(fields.stop_price),
        fields.time_in_force,
        str(fields.outside_hours),
        json.dumps(fields.attached_legs, sort_keys=True, default=str),
        str(fields.max_notional),
        str(fields.recommendation_version_id),
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_approval_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """True iff `expires_at` is strictly in the past relative to `now`
    (defaults to the current UTC time)."""
    now = now or datetime.now(UTC)
    return expires_at < now


def assert_can_transition_to_approved(
    current_status: str,
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> None:
    """Raise unless `current_status` may legally move to `APPROVED` *and*
    `expires_at` has not already passed. A DB row can be stuck showing
    `PENDING` past its `expires_at` if nothing has run the expiry sweep
    yet — this function fails closed on the wall-clock fact regardless
    of what the stored status says, so "expired approval cannot return
    an approved state" holds even against a stale row."""
    now = now or datetime.now(UTC)
    assert_transition_allowed(
        "OrderApproval",
        current_status,
        OrderApprovalStatus.APPROVED.value,
        ORDER_APPROVAL_TRANSITIONS,
    )
    if is_approval_expired(expires_at, now=now):
        raise ValueError(
            f"approval expired at {expires_at.isoformat()} (now {now.isoformat()}) — "
            "an expired approval cannot transition to APPROVED"
        )


def compute_effective_mode(db: Session, configured_mode: OrderAuthorityMode) -> OrderAuthorityMode:
    """OA-9: "an immediate trading kill switch... flips the effective
    operating mode to RESEARCH_ONLY." `configured_mode` (from
    `core.config.Settings.operating_mode`, R2) is what an operator has
    set; this function is what every order-authority check must
    actually gate against, so a kill switch fired seconds ago cannot be
    bypassed by a stale in-memory read of the configured mode."""
    latest = db.scalar(
        select(ExecutionKillSwitchEvent).order_by(ExecutionKillSwitchEvent.activated_at.desc())
    )
    if latest is not None and latest.deactivated_at is None:
        return OrderAuthorityMode.RESEARCH_ONLY
    return configured_mode


def is_kill_switch_active(db: Session) -> bool:
    """The same query `compute_effective_mode()` runs, exposed directly
    for callers (`services/order_execution.py::refresh_and_recalculate()`,
    `routers/settings.py`) that need the raw boolean rather than a mode
    override — avoids two slightly-different kill-switch queries
    existing side by side."""
    latest = db.scalar(
        select(ExecutionKillSwitchEvent).order_by(ExecutionKillSwitchEvent.activated_at.desc())
    )
    return latest is not None and latest.deactivated_at is None


def assert_broker_boundary_is_paper(
    *,
    account_type: AccountType,
    environment_label: EnvironmentLabel,
    broker_base_url: str,
) -> None:
    """OA-6 (fail-closed) applied specifically to "refuse live account
    IDs and live URLs" — the one check every call into
    `services/order_execution.py` runs *before* touching a
    `PaperBrokerProvider`, regardless of what any earlier policy
    evaluation already decided. Three independent facts must all agree
    this is paper-only; any one being wrong is an unconditional deny,
    never a best-guess pass-through (OA-6's own wording)."""
    if account_type is not AccountType.PAPER_ALPACA:
        raise OrderAuthorityDenied(
            f"only a PAPER_ALPACA account may reach the broker boundary (got {account_type.value})"
        )
    if environment_label is not EnvironmentLabel.PAPER:
        raise OrderAuthorityDenied(
            f"only environment_label=PAPER may reach the broker boundary "
            f"(got {environment_label.value})"
        )
    if "paper" not in broker_base_url.lower():
        raise OrderAuthorityDenied(
            f"broker_base_url does not look like a paper endpoint: {broker_base_url!r} — "
            "failing closed rather than guessing"
        )


def price_move_requires_invalidation(
    *,
    price_at_approval: Decimal,
    current_price: Decimal,
    threshold_pct: Decimal = DEFAULT_PRICE_MOVE_THRESHOLD_PCT,
) -> tuple[bool, Decimal]:
    """`(requires_invalidation, move_pct)` — `move_pct` is always
    returned (signed, positive = price rose) so a caller can record the
    exact move on the `ApprovalInvalidation` row even when it *doesn't*
    trigger one, for the same "explainable, not just a boolean" reason
    every other gate in this project records its own numbers."""
    if price_at_approval <= 0:
        raise ValueError("price_at_approval must be positive")
    move_pct = ((current_price - price_at_approval) / price_at_approval) * Decimal(100)
    return abs(move_pct) > threshold_pct, move_pct


def activate_kill_switch(
    db: Session, *, activated_by: str, reason: str | None, now: datetime
) -> ExecutionKillSwitchEvent:
    """Writes the kill-switch event and, in the same call, invalidates
    every still-`PENDING` approval (OA-9: "every in-flight
    APPROVAL_REQUIRED/AUTO_APPROVED order transitions to INVALIDATED,
    not left pending") — an already-`APPROVED` approval is untouched
    here (whether an in-flight *submission* should also be aborted is
    `services/order_execution.py`'s own re-check immediately before it
    calls the broker, not this function's job). Does not commit — the
    caller controls the transaction."""
    event = ExecutionKillSwitchEvent(activated_by=activated_by, activated_at=now, reason=reason)
    db.add(event)
    db.flush()

    pending_approvals = db.scalars(
        select(OrderApproval).where(OrderApproval.status == OrderApprovalStatus.PENDING)
    ).all()
    for approval in pending_approvals:
        approval.status = OrderApprovalStatus.INVALIDATED
        approval.decided_at = now
        db.add(
            ApprovalInvalidation(
                order_approval_id=approval.id,
                reason=ApprovalInvalidationReason.KILL_SWITCH,
                detail=f"kill switch activated by {activated_by}",
                invalidated_at=now,
            )
        )
    return event


def deactivate_kill_switch(
    db: Session, *, event: ExecutionKillSwitchEvent, now: datetime
) -> ExecutionKillSwitchEvent:
    """Deactivates a specific, already-activated event — the caller (the
    router) is responsible for resolving *which* event that is (normally
    the latest active one), keeping this function a pure state
    transition with no query of its own to disagree with the caller's."""
    if event.deactivated_at is not None:
        raise ValueError("kill switch event is already deactivated")
    event.deactivated_at = now
    return event
