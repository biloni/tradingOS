"""Tests for structured logging + redaction (Revision Prompt 16).

`caplog` captures records at the logger level, before they reach our
`JsonFormatter`/`RedactingFilter` (those live on a handler attached to
the root logger, which `caplog` bypasses) — so these tests exercise the
formatter/filter classes directly against synthetic `LogRecord`s rather
than trying to capture already-formatted stdout text, and separately
verify (via `caplog`) that the right log *messages* fire at the right
security-relevant call sites.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from tradingos_api.core.config import get_settings
from tradingos_api.core.logging import (
    JsonFormatter,
    RedactingFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)

_REQUEST_ID_HEADER = "X-Request-ID"


def _make_record(msg: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg=msg, args=(), exc_info=None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter:
    def test_produces_valid_json_with_expected_keys(self) -> None:
        formatter = JsonFormatter()
        record = _make_record("hello world")
        payload = json.loads(formatter.format(record))
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test"
        assert "timestamp" in payload
        assert "request_id" in payload

    def test_includes_extra_fields(self) -> None:
        formatter = JsonFormatter()
        record = _make_record("order event", order_id="abc123", status_code=200)
        payload = json.loads(formatter.format(record))
        assert payload["order_id"] == "abc123"
        assert payload["status_code"] == 200

    def test_includes_current_request_id(self) -> None:
        token = set_request_id("req-42")
        try:
            formatter = JsonFormatter()
            record = _make_record("hello")
            payload = json.loads(formatter.format(record))
            assert payload["request_id"] == "req-42"
        finally:
            reset_request_id(token)


class TestRedactingFilter:
    def test_redacts_known_secret_value_from_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret-value")
        get_settings.cache_clear()
        try:
            record = _make_record("calling provider with key sk-ant-super-secret-value")
            RedactingFilter().filter(record)
            assert "sk-ant-super-secret-value" not in record.getMessage()
            assert "[REDACTED]" in record.getMessage()
        finally:
            get_settings.cache_clear()

    def test_redacts_known_db_password_from_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+psycopg://app:sup3r-secret-pw@localhost:5432/tradingos"
        )
        get_settings.cache_clear()
        try:
            record = _make_record("connection failed for sup3r-secret-pw")
            RedactingFilter().filter(record)
            assert "sup3r-secret-pw" not in record.getMessage()
        finally:
            get_settings.cache_clear()

    def test_redacts_by_extra_field_name_regardless_of_value(self) -> None:
        record = _make_record("login attempt", password="whatever-the-value-is")
        RedactingFilter().filter(record)
        assert record.__dict__["password"] == "[REDACTED]"

    def test_non_sensitive_extra_fields_are_untouched(self) -> None:
        record = _make_record("order event", order_id="abc123", status_code=200)
        RedactingFilter().filter(record)
        assert record.__dict__["order_id"] == "abc123"
        assert record.__dict__["status_code"] == 200

    def test_returns_true_so_record_is_not_dropped(self) -> None:
        record = _make_record("hello")
        assert RedactingFilter().filter(record) is True


class TestRequestIdMiddleware:
    def test_response_carries_a_request_id_header(self, client: TestClient) -> None:
        response = client.get("/api/v1/portfolio/accounts")
        assert response.headers.get(_REQUEST_ID_HEADER)

    def test_request_id_is_unique_per_request(self, client: TestClient) -> None:
        first = client.get("/api/v1/portfolio/accounts").headers[_REQUEST_ID_HEADER]
        second = client.get("/api/v1/portfolio/accounts").headers[_REQUEST_ID_HEADER]
        assert first != second

    def test_request_id_context_is_cleared_between_requests(self, client: TestClient) -> None:
        client.get("/api/v1/portfolio/accounts")
        # Outside any request context (e.g. a background job importing
        # this module) there should never be a leftover request ID from
        # the last request the test process happened to handle.
        assert get_request_id() is None


class TestUnhandledExceptionHandler:
    def test_unexpected_exception_returns_generic_500_body(self) -> None:
        """A temporary route registered only for this test — deliberately
        not a monkeypatch of an existing handler, since FastAPI binds a
        route to the function object at decoration time (import time),
        not a dynamic by-name lookup a `monkeypatch.setattr` on the
        module would actually intercept. Uses its own `TestClient(...,
        raise_server_exceptions=False)`: Starlette's `ServerErrorMiddleware`
        builds the response via our registered handler *and* re-raises
        the original exception for in-process debugging, which is what
        a default TestClient surfaces — a real deployed server never
        does that (it only ever sends the HTTP response), so this flag
        is what makes the test see what a real client would."""
        from tradingos_api.main import app

        def _boom() -> None:
            raise RuntimeError("db exploded with secret-looking-value-xyz")

        route_path = "/__test_boom"
        app.add_api_route(route_path, _boom, methods=["GET"])
        try:
            with TestClient(app, raise_server_exceptions=False) as raw_client:
                response = raw_client.get(route_path)
        finally:
            app.router.routes = [
                r for r in app.router.routes if getattr(r, "path", None) != route_path
            ]

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error."}
        assert "secret-looking-value-xyz" not in response.text


class TestAuthSecurityLogging:
    def test_login_failure_is_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="tradingos_api.security"):
            client.post("/api/v1/auth/login", json={"password": "definitely-wrong"})
        assert any("login failed" in record.message for record in caplog.records)

    def test_logout_success_is_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="tradingos_api.security"):
            client.post("/api/v1/auth/logout")
        assert any("session revoked" in record.message for record in caplog.records)
