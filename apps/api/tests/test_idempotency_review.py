"""Router-level tests for the Revision Prompt 16 idempotency review:
confirm/cancel/cancel-open's replay behavior (regression-proofing that
adding `with_for_update()` row locks didn't change the sequential-
replay contract) and reconcile's new idempotency-key support end to end
through the HTTP layer (service-level coverage lives in
tests/test_reconciliation.py)."""

from __future__ import annotations

import uuid
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account

from .conftest import TEST_PASSWORD


def _propose_and_confirm(
    client: TestClient,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    side: str,
    qty: str,
    price: str,
) -> dict[str, Any]:
    propose = client.post(
        "/api/v1/orders",
        json={
            "account_id": str(account_id),
            "instrument_id": str(instrument_id),
            "side": side,
            "order_type": "MARKET",
            "quantity": qty,
            "limit_price": price,
        },
    )
    assert propose.status_code == 201, propose.text
    order_id = propose.json()["id"]
    confirm = client.post(f"/api/v1/orders/{order_id}/confirm")
    assert confirm.status_code == 200, confirm.text
    return cast(dict[str, Any], confirm.json())


class TestConfirmCancelReplayStillWorksAfterRowLocking:
    def test_a_second_confirm_400s_cleanly(
        self, client: TestClient, fresh_account: Account, seeded_instrument_id: uuid.UUID
    ) -> None:
        order = _propose_and_confirm(
            client, fresh_account.id, seeded_instrument_id, "BUY", "1", "100.00"
        )
        replay = client.post(f"/api/v1/orders/{order['id']}/confirm")
        assert replay.status_code == 400

    def test_a_second_cancel_400s_cleanly(
        self, client: TestClient, fresh_account: Account, seeded_instrument_id: uuid.UUID
    ) -> None:
        propose = client.post(
            "/api/v1/orders",
            json={
                "account_id": str(fresh_account.id),
                "instrument_id": str(seeded_instrument_id),
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": "1",
                "limit_price": "100.00",
            },
        )
        order_id = propose.json()["id"]
        first = client.post(f"/api/v1/orders/{order_id}/cancel")
        assert first.status_code == 200
        second = client.post(f"/api/v1/orders/{order_id}/cancel")
        assert second.status_code == 400


class TestReconcileIdempotencyThroughTheRouter:
    def test_repeated_key_returns_the_same_run_marked_replayed(
        self, client: TestClient, db_session: Session
    ) -> None:
        account = db_session.scalar(select(Account).limit(1))
        assert account is not None

        first = client.post(
            f"/api/v1/portfolio/accounts/{account.id}/reconcile",
            json={"broker_reported_positions": {}, "idempotency_key": "router-test-key"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["replayed"] is False

        second = client.post(
            f"/api/v1/portfolio/accounts/{account.id}/reconcile",
            json={"broker_reported_positions": {}, "idempotency_key": "router-test-key"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["replayed"] is True
        assert second.json()["id"] == first.json()["id"]

    def test_no_key_behaves_exactly_as_before(
        self, client: TestClient, db_session: Session
    ) -> None:
        account = db_session.scalar(select(Account).limit(1))
        assert account is not None

        response = client.post(
            f"/api/v1/portfolio/accounts/{account.id}/reconcile",
            json={"broker_reported_positions": {}},
        )
        assert response.status_code == 200
        assert response.json()["replayed"] is False


class TestCancelOpenIsANoOpOnReplay:
    def test_calling_cancel_open_twice_cancels_nothing_the_second_time(
        self, client: TestClient, fresh_account: Account, seeded_instrument_id: uuid.UUID
    ) -> None:
        step_up = client.post("/api/v1/auth/step-up", json={"password": TEST_PASSWORD})
        assert step_up.status_code == 200, step_up.text

        first = client.post(
            "/api/v1/orders/cancel-open",
            json={"account_id": str(fresh_account.id), "triggered_by": "test"},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/orders/cancel-open",
            json={"account_id": str(fresh_account.id), "triggered_by": "test"},
        )
        assert second.status_code == 200
        assert second.json()["orders_canceled_count"] == 0
