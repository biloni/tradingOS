"""Approval-integrity-hash and expiration tests (Revision Prompt R3,
ADR-048). Pure unit tests — no DB — matching this repo's existing
fixtures-only test policy (docs/TEST_STRATEGY.md)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradingos_api.models.enums import OrderApprovalStatus
from tradingos_api.services.lifecycle import InvalidTransitionError
from tradingos_api.services.order_authority import (
    BoundFieldsSnapshot,
    assert_can_transition_to_approved,
    compute_bound_fields_hash,
    is_approval_expired,
)

NOW = datetime(2026, 8, 5, 13, 0, tzinfo=UTC)


def _snapshot(**overrides: object) -> BoundFieldsSnapshot:
    defaults: dict[str, object] = {
        "account_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "instrument_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "side": "BUY",
        "quantity": Decimal("10"),
        "order_type": "LIMIT",
        "limit_price": Decimal("123.45"),
        "stop_price": None,
        "time_in_force": "DAY",
        "outside_hours": False,
        "attached_legs": {},
        "max_notional": None,
        "recommendation_version_id": None,
    }
    defaults.update(overrides)
    return BoundFieldsSnapshot(**defaults)  # type: ignore[arg-type]


class TestApprovalHashChangesWithBoundFields:
    def test_identical_snapshots_hash_identically(self) -> None:
        assert compute_bound_fields_hash(_snapshot()) == compute_bound_fields_hash(_snapshot())

    def test_quantity_change_changes_hash(self) -> None:
        base = compute_bound_fields_hash(_snapshot())
        changed = compute_bound_fields_hash(_snapshot(quantity=Decimal("11")))
        assert base != changed

    def test_limit_price_change_changes_hash(self) -> None:
        base = compute_bound_fields_hash(_snapshot())
        changed = compute_bound_fields_hash(_snapshot(limit_price=Decimal("999.99")))
        assert base != changed

    def test_side_change_changes_hash(self) -> None:
        base = compute_bound_fields_hash(_snapshot())
        changed = compute_bound_fields_hash(_snapshot(side="SELL"))
        assert base != changed

    def test_attached_legs_change_changes_hash(self) -> None:
        base = compute_bound_fields_hash(_snapshot())
        changed = compute_bound_fields_hash(_snapshot(attached_legs={"STOP_LOSS": "10.00"}))
        assert base != changed

    def test_recommendation_version_id_change_changes_hash(self) -> None:
        base = compute_bound_fields_hash(_snapshot())
        changed = compute_bound_fields_hash(
            _snapshot(recommendation_version_id=uuid.UUID("33333333-3333-3333-3333-333333333333"))
        )
        assert base != changed


class TestExpiredApprovalCannotReturnToApproved:
    def test_pending_before_expiry_may_approve(self) -> None:
        assert_can_transition_to_approved(
            OrderApprovalStatus.PENDING.value,
            NOW + timedelta(minutes=5),
            now=NOW,
        )

    def test_pending_past_expiry_is_denied_even_if_status_not_yet_marked_expired(self) -> None:
        with pytest.raises(ValueError, match="expired"):
            assert_can_transition_to_approved(
                OrderApprovalStatus.PENDING.value,
                NOW - timedelta(minutes=1),
                now=NOW,
            )

    def test_already_expired_status_is_denied(self) -> None:
        with pytest.raises(InvalidTransitionError):
            assert_can_transition_to_approved(
                OrderApprovalStatus.EXPIRED.value,
                NOW + timedelta(minutes=5),
                now=NOW,
            )

    def test_already_invalidated_status_is_denied(self) -> None:
        with pytest.raises(InvalidTransitionError):
            assert_can_transition_to_approved(
                OrderApprovalStatus.INVALIDATED.value,
                NOW + timedelta(minutes=5),
                now=NOW,
            )

    def test_is_approval_expired_helper(self) -> None:
        assert is_approval_expired(NOW - timedelta(seconds=1), now=NOW) is True
        assert is_approval_expired(NOW + timedelta(seconds=1), now=NOW) is False
