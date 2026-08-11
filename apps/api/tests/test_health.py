from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
from tradingos_api.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "time_utc" in body


class TestReadiness:
    """Revision Prompt 16 — `/ready` reports every dependency this app
    actually has, honestly. Uses env-driven `Settings` overrides (like
    `test_settings.py`) rather than relying on whatever `apps/api/.env`
    happens to contain, so these tests don't depend on this developer's
    local credential setup."""

    def test_ready_reports_all_expected_dependency_keys(self) -> None:
        response = client.get("/ready")
        body = response.json()
        assert set(body["checks"].keys()) == {
            "database",
            "market_data_provider",
            "broker_provider",
            "llm_provider",
            "scheduler",
            "worker",
        }

    def test_database_reachable_reports_ok_and_200(self) -> None:
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["checks"]["database"]["status"] == "ok"

    def test_database_unreachable_reports_error_and_503(self) -> None:
        class _BrokenSession:
            def execute(self, *args: object, **kwargs: object) -> None:
                raise RuntimeError("connection refused")

        def _override_get_db() -> Iterator[Session]:
            yield _BrokenSession()  # type: ignore[misc]

        app.dependency_overrides[get_db] = _override_get_db
        try:
            response = client.get("/ready")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["checks"]["database"]["status"] == "error"
        assert "connection refused" in body["checks"]["database"]["detail"]

    def test_providers_configured_when_credentials_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        get_settings.cache_clear()
        try:
            response = client.get("/ready")
            body = response.json()
            assert body["checks"]["market_data_provider"]["status"] == "configured"
            assert body["checks"]["broker_provider"]["status"] == "configured"
            assert body["checks"]["llm_provider"]["status"] == "configured"
        finally:
            get_settings.cache_clear()

    def test_providers_not_configured_absent_missing_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `monkeypatch.delenv` alone wouldn't be enough here: pydantic-settings
        # falls back to `apps/api/.env` for any field missing from the OS
        # environment, so a real credential configured there would still
        # win. Setting an explicit empty string overrides both.
        monkeypatch.setenv("ALPACA_API_KEY_ID", "")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        get_settings.cache_clear()
        try:
            response = client.get("/ready")
            body = response.json()
            assert body["checks"]["market_data_provider"]["status"] == "not_configured"
            assert body["checks"]["broker_provider"]["status"] == "not_configured"
            assert body["checks"]["llm_provider"]["status"] == "not_configured"
        finally:
            get_settings.cache_clear()

    def test_missing_provider_credentials_do_not_block_readiness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing Alpaca/Anthropic key is a real, reportable fact —
        but this app is built to degrade gracefully without them
        (principle 5), so it must never fail the overall readiness
        check the way a genuinely down database does."""
        # `monkeypatch.delenv` alone wouldn't be enough here: pydantic-settings
        # falls back to `apps/api/.env` for any field missing from the OS
        # environment, so a real credential configured there would still
        # win. Setting an explicit empty string overrides both.
        monkeypatch.setenv("ALPACA_API_KEY_ID", "")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        get_settings.cache_clear()
        try:
            response = client.get("/ready")
            assert response.status_code == 200
            assert response.json()["ready"] is True
        finally:
            get_settings.cache_clear()

    def test_scheduler_and_worker_report_not_running_under_the_test_process(self) -> None:
        """`core/scheduler.py`'s in-process APScheduler only starts from
        the app's lifespan (`main.py`), which `TestClient(app)` never
        triggers unless entered as a context manager — this project's
        `client` fixture deliberately never does that (see
        `core/scheduler.py`'s own docstring), so under pytest the
        honest status is `not_running`, not a faked `ok`."""
        response = client.get("/ready")
        body = response.json()
        assert body["checks"]["scheduler"]["status"] == "not_running"
        assert body["checks"]["worker"]["status"] == "not_running"

    def test_ready_is_reachable_without_authentication(self) -> None:
        """An infra orchestrator's readiness probe has no session
        cookie — `/ready` must never be gated by `require_session`
        (mirrors `/health`)."""
        response = client.get("/ready")
        assert response.status_code in (200, 503)
