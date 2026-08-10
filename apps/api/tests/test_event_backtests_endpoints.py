"""Event-backtest router smoke tests (Revision Prompt 13) — run/list/
detail/compare/download/reports all against real Postgres state."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _run_payload(strategy_key: str = "SPY_BUY_AND_HOLD") -> dict[str, str]:
    return {
        "strategy_key": strategy_key,
        "start": "2026-02-03",
        "end": "2026-07-31",
        "universe_start": "2024-08-01",
        "universe_end": "2026-07-31",
    }


class TestTriggerAndDetail:
    def test_trigger_run_returns_201_with_trades(self, client: TestClient) -> None:
        response = client.post("/api/v1/event-backtests/run", json=_run_payload())
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["strategy_key"] == "SPY_BUY_AND_HOLD"
        assert len(body["trades"]) >= 1
        assert body["equity_curve"][0]["equity"] == "10000"

    def test_detail_matches_the_triggered_run(self, client: TestClient) -> None:
        created = client.post("/api/v1/event-backtests/run", json=_run_payload())
        run_id = created.json()["id"]
        response = client.get(f"/api/v1/event-backtests/{run_id}")
        assert response.status_code == 200
        assert response.json()["id"] == run_id

    def test_detail_unknown_run_is_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/event-backtests/{uuid.uuid4()}")
        assert response.status_code == 404


class TestListAndCompare:
    def test_list_includes_triggered_run(self, client: TestClient) -> None:
        created = client.post("/api/v1/event-backtests/run", json=_run_payload())
        run_id = created.json()["id"]
        response = client.get("/api/v1/event-backtests", params={"limit": 50})
        assert response.status_code == 200
        assert any(item["id"] == run_id for item in response.json()["items"])

    def test_compare_two_runs(self, client: TestClient) -> None:
        first = client.post("/api/v1/event-backtests/run", json=_run_payload("SPY_BUY_AND_HOLD"))
        second = client.post(
            "/api/v1/event-backtests/run", json=_run_payload("EMA_CROSS_COMPARISON")
        )
        response = client.get(
            "/api/v1/event-backtests/compare",
            params=[("run_ids", first.json()["id"]), ("run_ids", second.json()["id"])],
        )
        assert response.status_code == 200
        assert len(response.json()["runs"]) == 2

    def test_compare_unknown_run_is_404(self, client: TestClient) -> None:
        created = client.post("/api/v1/event-backtests/run", json=_run_payload())
        run_id = created.json()["id"]
        response = client.get(
            "/api/v1/event-backtests/compare",
            params=[("run_ids", run_id), ("run_ids", str(uuid.uuid4()))],
        )
        assert response.status_code == 404


class TestDownload:
    def test_download_returns_csv(self, client: TestClient) -> None:
        created = client.post("/api/v1/event-backtests/run", json=_run_payload())
        run_id = created.json()["id"]
        response = client.get(f"/api/v1/event-backtests/{run_id}/download")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "instrument_id" in response.text.splitlines()[0]


class TestReports:
    def test_baseline_reproduction_report(self, client: TestClient) -> None:
        response = client.get("/api/v1/event-backtests/reports/baseline-reproduction")
        assert response.status_code == 200
        body = response.json()
        assert "targets" in body
        assert body["targets"]["num_trades"] == 25

    def test_go_no_go_report(self, client: TestClient) -> None:
        response = client.get("/api/v1/event-backtests/reports/go-no-go")
        assert response.status_code == 200
        body = response.json()
        assert len(body["strategy_comparison"]) == 8
        assert body["recommendation"]
        assert len(body["bias_and_quality_caveats"]) > 0
