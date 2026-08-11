"""Tests for the auth endpoints and the CSRF gate (Revision Prompt 16,
ADR-066). The `client` fixture (tests/conftest.py) already exercises the
login->authenticated-request happy path implicitly on every other test
file in this suite; this file covers the auth endpoints themselves plus
the negative/edge cases nothing else touches: wrong password, missing
CSRF token, tampered CSRF token, session expiry/logout, and step-up.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.auth import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from tradingos_api.core.auth import hash_password as _hash_password
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.identity import UserProfile
from tradingos_api.routers.auth import login_rate_limiter

TEST_PASSWORD = "another-test-password-not-real"


@pytest.fixture
def raw_client(db_session: Session) -> Iterator[TestClient]:
    """Unlike the `client` fixture, does NOT log in — every test in this
    file drives login/logout/CSRF itself."""

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    login_rate_limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _set_password(db_session: Session, password: str = TEST_PASSWORD) -> None:
    user = db_session.scalar(select(UserProfile))
    assert user is not None, "seed data must exist (run `tradingos-seed`)"
    user.password_hash = _hash_password(password)
    db_session.flush()


class TestLogin:
    def test_wrong_password_is_rejected(self, raw_client: TestClient, db_session: Session) -> None:
        _set_password(db_session)
        response = raw_client.post("/api/v1/auth/login", json={"password": "not-it"})
        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in raw_client.cookies

    def test_no_password_configured_is_rejected(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        user = db_session.scalar(select(UserProfile))
        assert user is not None
        user.password_hash = None
        db_session.flush()
        response = raw_client.post("/api/v1/auth/login", json={"password": "anything"})
        assert response.status_code == 401

    def test_correct_password_sets_session_and_csrf_cookies(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        response = raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is True
        assert body["stepped_up"] is False
        assert raw_client.cookies.get(SESSION_COOKIE_NAME)
        assert raw_client.cookies.get(CSRF_COOKIE_NAME)
        # The two must be different — the CSRF value must never double as
        # (or be derivable from) the session token.
        assert raw_client.cookies.get(SESSION_COOKIE_NAME) != raw_client.cookies.get(
            CSRF_COOKIE_NAME
        )

    def test_rate_limited_after_repeated_attempts(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        for _ in range(5):
            raw_client.post("/api/v1/auth/login", json={"password": "wrong"})
        response = raw_client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert response.status_code == 429


class TestSessionStatus:
    def test_no_cookie_reports_unauthenticated(self, raw_client: TestClient) -> None:
        response = raw_client.get("/api/v1/auth/session")
        assert response.status_code == 200
        assert response.json() == {"authenticated": False, "stepped_up": False, "expires_at": None}

    def test_after_login_reports_authenticated(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        response = raw_client.get("/api/v1/auth/session")
        body = response.json()
        assert body["authenticated"] is True
        assert body["stepped_up"] is False
        assert body["expires_at"]


class TestCsrfGate:
    """Every gated router shares `require_session()`, so exercising it
    once against a representative endpoint (`GET /portfolio/accounts`
    for reads, `PATCH /settings/risk-policy` for a write — a pure DB
    write with no broker/network call, so a non-403 result is
    unambiguous) proves the gate itself works — it doesn't need to be
    repeated per-router."""

    def test_write_without_csrf_header_is_rejected(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        # A valid session cookie is present (httpx carries it automatically)
        # but no X-CSRF-Token header was ever set on this client.
        response = raw_client.patch("/api/v1/settings/risk-policy", json={})
        assert response.status_code == 403

    def test_write_with_wrong_csrf_header_is_rejected(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        response = raw_client.patch(
            "/api/v1/settings/risk-policy",
            json={},
            headers={CSRF_HEADER_NAME: "not-the-real-token"},
        )
        assert response.status_code == 403

    def test_write_with_correct_csrf_header_passes_the_gate(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        csrf_token = raw_client.cookies.get(CSRF_COOKIE_NAME)
        assert csrf_token
        # A pure-DB PATCH (no broker/network call, unlike cancel-open) so
        # a 200 here is unambiguous proof the CSRF gate itself passed —
        # every field is optional, so an empty body is a genuine no-op update.
        response = raw_client.patch(
            "/api/v1/settings/risk-policy",
            json={},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert response.status_code == 200

    def test_reads_never_require_a_csrf_header(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        response = raw_client.get("/api/v1/portfolio/accounts")
        assert response.status_code == 200


class TestLogout:
    def test_logout_revokes_the_session(self, raw_client: TestClient, db_session: Session) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        csrf_token = raw_client.cookies.get(CSRF_COOKIE_NAME)
        logout_response = raw_client.post(
            "/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf_token or ""}
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["authenticated"] is False

        status_response = raw_client.get("/api/v1/auth/session")
        assert status_response.json()["authenticated"] is False

        gated_response = raw_client.get("/api/v1/portfolio/accounts")
        assert gated_response.status_code == 401


class TestStepUp:
    def test_correct_password_marks_stepped_up(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        csrf_token = raw_client.cookies.get(CSRF_COOKIE_NAME)
        response = raw_client.post(
            "/api/v1/auth/step-up",
            json={"password": TEST_PASSWORD},
            headers={CSRF_HEADER_NAME: csrf_token or ""},
        )
        assert response.status_code == 200
        assert response.json()["stepped_up"] is True

        status_response = raw_client.get("/api/v1/auth/session")
        assert status_response.json()["stepped_up"] is True

    def test_wrong_password_is_rejected(self, raw_client: TestClient, db_session: Session) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        csrf_token = raw_client.cookies.get(CSRF_COOKIE_NAME)
        response = raw_client.post(
            "/api/v1/auth/step-up",
            json={"password": "wrong"},
            headers={CSRF_HEADER_NAME: csrf_token or ""},
        )
        assert response.status_code == 401

    def test_requires_an_existing_session(self, raw_client: TestClient) -> None:
        response = raw_client.post("/api/v1/auth/step-up", json={"password": TEST_PASSWORD})
        assert response.status_code == 401


class TestSecurityHeaders:
    def test_response_carries_hardening_headers(
        self, raw_client: TestClient, db_session: Session
    ) -> None:
        _set_password(db_session)
        raw_client.post("/api/v1/auth/login", json={"password": TEST_PASSWORD})
        response = raw_client.get("/api/v1/portfolio/accounts")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
        assert "content-security-policy" in response.headers
        # Local dev is plain HTTP — HSTS would be a lie the browser can't act on.
        assert "strict-transport-security" not in response.headers

    def test_docs_route_is_exempt_from_csp(self, raw_client: TestClient) -> None:
        response = raw_client.get("/docs")
        assert "content-security-policy" not in response.headers
        # The rest of the hardening headers still apply everywhere.
        assert response.headers["x-content-type-options"] == "nosniff"
