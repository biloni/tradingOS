"""Tests for the job dashboard + metrics endpoints (Revision Prompt 16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.core.metrics import request_metrics
from tradingos_api.models.enums import MorningPlanRunStatus
from tradingos_api.models.morning_plan import MorningPlanRun

_PLAN_DATE = datetime(2026, 8, 11).date()


def _make_run(
    db: Session,
    *,
    status: MorningPlanRunStatus,
    started_at: datetime,
    completed_at: datetime | None = None,
    error_detail: str | None = None,
) -> MorningPlanRun:
    run = MorningPlanRun(
        plan_date=_PLAN_DATE,
        triggered_by="test",
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        error_detail=error_detail,
    )
    db.add(run)
    db.flush()
    return run


class TestSchedulerStatus:
    def test_reports_not_running_under_the_test_process(self, client: TestClient) -> None:
        """Mirrors `test_health.py`'s readiness assertion — the app's
        lifespan (where `core/scheduler.py::start_scheduler()` is
        called) never runs under `TestClient(app)` unless entered as a
        context manager, which this project's `client` fixture
        deliberately never does."""
        response = client.get("/api/v1/ops/scheduler")
        assert response.status_code == 200
        body = response.json()
        assert body["running"] is False
        assert body["tick_interval_seconds"] == 60
        assert body["tick_count"] == 0
        assert body["last_tick_at"] is None


class TestMetrics:
    def test_metrics_endpoint_returns_expected_shape(self, client: TestClient) -> None:
        response = client.get("/api/v1/ops/metrics")
        assert response.status_code == 200
        body = response.json()
        assert body["total_requests"] >= 1  # this very request was counted
        assert set(body["status_class_counts"].keys()) <= {"1xx", "2xx", "3xx", "4xx", "5xx"}
        assert "avg_ms" in body["latency"]
        assert "p95_ms" in body["latency"]
        assert body["latency"]["sample_size"] >= 1

    def test_requests_increment_the_total_count(self, client: TestClient) -> None:
        before = client.get("/api/v1/ops/metrics").json()["total_requests"]
        client.get("/api/v1/ops/metrics")
        after = client.get("/api/v1/ops/metrics").json()["total_requests"]
        assert after > before

    def test_collector_snapshot_is_read_only(self) -> None:
        """Calling `snapshot()` twice must not itself change counts —
        only real requests recorded via `record()` should."""
        first = request_metrics.snapshot()["total_requests"]
        second = request_metrics.snapshot()["total_requests"]
        assert first == second


class TestJobRuns:
    def test_lists_runs_most_recent_first(self, client: TestClient, db_session: Session) -> None:
        older = _make_run(
            db_session,
            status=MorningPlanRunStatus.COMPLETED,
            started_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
        newer = _make_run(
            db_session,
            status=MorningPlanRunStatus.COMPLETED,
            started_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
        db_session.commit()

        response = client.get("/api/v1/ops/job-runs")
        assert response.status_code == 200
        ids = [row["id"] for row in response.json()]
        assert ids.index(str(newer.id)) < ids.index(str(older.id))

    def test_completed_run_reports_duration(self, client: TestClient, db_session: Session) -> None:
        started = datetime(2026, 8, 11, 6, 10, tzinfo=UTC)
        run = _make_run(
            db_session,
            status=MorningPlanRunStatus.COMPLETED,
            started_at=started,
            completed_at=started + timedelta(seconds=42),
        )
        db_session.commit()

        response = client.get("/api/v1/ops/job-runs")
        row = next(r for r in response.json() if r["id"] == str(run.id))
        assert row["duration_seconds"] == 42.0
        assert row["status"] == "COMPLETED"

    def test_running_run_has_no_duration_yet(self, client: TestClient, db_session: Session) -> None:
        run = _make_run(
            db_session, status=MorningPlanRunStatus.RUNNING, started_at=datetime.now(UTC)
        )
        db_session.commit()

        response = client.get("/api/v1/ops/job-runs")
        row = next(r for r in response.json() if r["id"] == str(run.id))
        assert row["duration_seconds"] is None
        assert row["completed_at"] is None

    def test_failed_run_surfaces_error_detail(
        self, client: TestClient, db_session: Session
    ) -> None:
        started = datetime(2026, 8, 11, 5, 45, tzinfo=UTC)
        run = _make_run(
            db_session,
            status=MorningPlanRunStatus.FAILED,
            started_at=started,
            completed_at=started + timedelta(seconds=5),
            error_detail="provider timeout",
        )
        db_session.commit()

        response = client.get("/api/v1/ops/job-runs")
        row = next(r for r in response.json() if r["id"] == str(run.id))
        assert row["status"] == "FAILED"
        assert row["error_detail"] == "provider timeout"

    def test_limit_is_capped_at_100(self, client: TestClient) -> None:
        response = client.get("/api/v1/ops/job-runs?limit=99999")
        assert response.status_code == 200
        assert len(response.json()) <= 100

    def test_requires_authentication(self) -> None:
        from fastapi.testclient import TestClient as RawTestClient

        from tradingos_api.main import app

        raw_client = RawTestClient(app)
        response = raw_client.get("/api/v1/ops/job-runs")
        assert response.status_code == 401
