"""Tests for the Revision Prompt R2 operating-mode scaffold endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tradingos_api.core.config import get_settings
from tradingos_api.main import app

client = TestClient(app)


class TestOperatingModeEndpoint:
    def test_defaults_to_research_only(self) -> None:
        get_settings.cache_clear()
        response = client.get("/api/v1/settings/operating-mode")
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "mode": "RESEARCH_ONLY",
            "environment_label": "RESEARCH",
            "can_submit_orders": False,
        }

    def test_reports_paper_mode_environment_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPERATING_MODE", "PAPER_MANUAL_APPROVAL")
        get_settings.cache_clear()
        try:
            response = client.get("/api/v1/settings/operating-mode")
            body = response.json()
            assert body["mode"] == "PAPER_MANUAL_APPROVAL"
            assert body["environment_label"] == "PAPER"
            assert body["can_submit_orders"] is True
        finally:
            get_settings.cache_clear()

    def test_reports_live_mode_environment_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPERATING_MODE", "LIVE_CONFIRM_EACH_ORDER")
        get_settings.cache_clear()
        try:
            response = client.get("/api/v1/settings/operating-mode")
            body = response.json()
            assert body["mode"] == "LIVE_CONFIRM_EACH_ORDER"
            assert body["environment_label"] == "LIVE"
            assert body["can_submit_orders"] is True
        finally:
            get_settings.cache_clear()

    def test_unknown_value_fails_closed_to_research_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPERATING_MODE", "SOMETHING_INVALID")
        get_settings.cache_clear()
        try:
            response = client.get("/api/v1/settings/operating-mode")
            body = response.json()
            assert body["mode"] == "RESEARCH_ONLY"
            assert body["can_submit_orders"] is False
        finally:
            get_settings.cache_clear()
