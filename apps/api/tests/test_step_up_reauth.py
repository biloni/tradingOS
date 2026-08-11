"""Tests for step-up re-authentication on sensitive actions (Revision
Prompt 16): kill-switch deactivate, cancel-open-orders, and order
approval approve/submit each require a fresh (<=5min) password
re-confirmation on top of an already-valid session, via
`core/dependencies.py::require_step_up()`. Kill-switch *activate* is
deliberately exempt (the emergency brake must stay one click) and
reject/expire/invalidate are exempt (they only reduce risk) — this file
proves both the gated and the exempt endpoints behave as designed.

Uses `raw_client` (mirrors tests/test_auth_endpoints.py) rather than the
auto-stepped-up `client` fixture, since these tests need to control
step-up state precisely.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.auth import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tradingos_api.core.auth import hash_password as _hash_password
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.routers.auth import login_rate_limiter

TEST_PASSWORD = "step-up-test-password-not-real"


@pytest.fixture
def raw_client(db_session: Session) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    login_rate_limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def logged_in_client(raw_client: TestClient, db_session: Session) -> TestClient:
    """Authenticated but NOT stepped up — the state every sensitive
    action starts from after a plain login."""
    user = db_session.scalar(select(UserProfile))
    assert user is not None
    user.password_hash = _hash_password(TEST_PASSWORD)
    db_session.flush()
    login_response = raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
    assert login_response.status_code == 200
    csrf_token = raw_client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf_token
    raw_client.headers[CSRF_HEADER_NAME] = csrf_token
    return raw_client


def _step_up(client: TestClient) -> None:
    response = client.post("/api/v1/auth/step-up", json={"password": TEST_PASSWORD})
    assert response.status_code == 200, response.text


class TestKillSwitch:
    def test_activate_never_requires_step_up(self, logged_in_client: TestClient) -> None:
        """The emergency brake must stay a single click — no step-up."""
        response = logged_in_client.post(
            "/api/v1/settings/kill-switch/activate",
            json={"activated_by": "test", "reason": "test"},
        )
        assert response.status_code == 201

    def test_deactivate_without_step_up_is_rejected(self, logged_in_client: TestClient) -> None:
        logged_in_client.post(
            "/api/v1/settings/kill-switch/activate",
            json={"activated_by": "test", "reason": "test"},
        )
        response = logged_in_client.post("/api/v1/settings/kill-switch/deactivate")
        assert response.status_code == 403

    def test_deactivate_with_step_up_succeeds(self, logged_in_client: TestClient) -> None:
        logged_in_client.post(
            "/api/v1/settings/kill-switch/activate",
            json={"activated_by": "test", "reason": "test"},
        )
        _step_up(logged_in_client)
        response = logged_in_client.post("/api/v1/settings/kill-switch/deactivate")
        assert response.status_code == 200


class TestCancelOpenOrders:
    def test_without_step_up_is_rejected(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(
            "/api/v1/orders/cancel-open", json={"triggered_by": "test"}
        )
        assert response.status_code == 403

    def test_with_step_up_passes_the_gate(
        self, logged_in_client: TestClient, fresh_account: Account
    ) -> None:
        # Scoped to a fresh, order-free MANUAL account — omitting
        # account_id would sweep every PAPER_ALPACA account, including
        # seed data holding a real (long-dead) Alpaca paper order id,
        # which would attempt a live network call and fail on a 404
        # from Alpaca unrelated to what this test is actually proving.
        _step_up(logged_in_client)
        response = logged_in_client.post(
            "/api/v1/orders/cancel-open",
            json={"account_id": str(fresh_account.id), "triggered_by": "test"},
        )
        assert response.status_code == 200


class TestOrderApprovalDecisions:
    """No approval fixture is built here (no factory for the full
    proposal->approval chain exists yet — a pre-existing gap, not
    introduced by this task). A nonexistent `approval_id` still proves
    the gate: `require_step_up` runs as a dependency and short-circuits
    with 403 before the endpoint body ever looks up the row, so a
    without-step-up request never reaches "not found"; a with-step-up
    request passes the gate and reaches the endpoint's own 404."""

    def test_approve_without_step_up_never_reaches_the_endpoint(
        self, logged_in_client: TestClient
    ) -> None:
        response = logged_in_client.post(
            f"/api/v1/order-approvals/{uuid.uuid4()}/approve",
            json={"approved_by": "test"},
        )
        assert response.status_code == 403

    def test_approve_with_step_up_passes_the_gate(self, logged_in_client: TestClient) -> None:
        _step_up(logged_in_client)
        response = logged_in_client.post(
            f"/api/v1/order-approvals/{uuid.uuid4()}/approve",
            json={"approved_by": "test"},
        )
        assert response.status_code == 404

    def test_reject_never_requires_step_up(self, logged_in_client: TestClient) -> None:
        """Reject only ever reduces risk — exempt by design."""
        response = logged_in_client.post(f"/api/v1/order-approvals/{uuid.uuid4()}/reject")
        assert response.status_code == 404

    def test_expire_never_requires_step_up(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(f"/api/v1/order-approvals/{uuid.uuid4()}/expire")
        assert response.status_code == 404

    def test_invalidate_never_requires_step_up(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(
            f"/api/v1/order-approvals/{uuid.uuid4()}/invalidate",
            json={"reason": "MANUAL"},
        )
        assert response.status_code == 404


class TestOrderSubmit:
    """Same nonexistent-ID technique as TestOrderApprovalDecisions — the
    single most sensitive endpoint in the codebase (the only HTTP route
    that reaches a broker), so it's covered separately for emphasis."""

    _PAYLOAD = {"requested_mode": "PAPER_MANUAL_APPROVAL"}

    def test_without_step_up_never_reaches_the_endpoint(self, logged_in_client: TestClient) -> None:
        response = logged_in_client.post(
            f"/api/v1/order-approvals/{uuid.uuid4()}/submit", json=self._PAYLOAD
        )
        assert response.status_code == 403

    def test_with_step_up_passes_the_gate(self, logged_in_client: TestClient) -> None:
        _step_up(logged_in_client)
        response = logged_in_client.post(
            f"/api/v1/order-approvals/{uuid.uuid4()}/submit", json=self._PAYLOAD
        )
        assert response.status_code == 404
