"""Approval-integrity and expiration logic for `OrderApproval`/
`ApprovalBoundFields` (ADR-048, Revision Prompt R3).

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

from tradingos_api.models.enums import ORDER_APPROVAL_TRANSITIONS, OrderApprovalStatus
from tradingos_api.services.lifecycle import assert_transition_allowed


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
