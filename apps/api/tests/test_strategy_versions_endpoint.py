"""`/api/v1/strategy-versions` endpoint tests run against an in-memory
SQLite database with a minimal `PriceBar` fixture — no live Postgres, per
the project's fixtures-not-live-APIs test policy (same pattern as
test_backtest_endpoint.py). Indicators are intentionally omitted: a
missing indicator resolves to a neutral signal (services/scoring.py), so
a plain price series is enough for run_backtest() to complete — these
tests are about the propose/compare/approve/reject state machine and
audit trail, not backtest correctness (already covered thoroughly by
test_backtest_simulation.py/test_backtest_endpoint.py)."""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingos_api.db.base import Base
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.audit_event import AuditEvent
from tradingos_api.models.backtest_run import BacktestRun
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.strategy_version import StrategyVersion, StrategyVersionStatus
from tradingos_api.models.symbol import AssetType, Symbol

D0 = date(2026, 1, 5)
D_END = D0 + timedelta(days=5)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    aapl = Symbol(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
        active=True,
    )
    session.add(aapl)
    session.commit()
    session.refresh(aapl)

    for i in range(6):
        session.add(
            PriceBar(
                symbol_id=aapl.id,
                as_of=D0 + timedelta(days=i),
                timeframe=Timeframe.DAY,
                open=Decimal(100 + i),
                high=Decimal(101 + i),
                low=Decimal(99 + i),
                close=Decimal(100 + i),
                volume=1000,
                source="test",
                adjustment="split",
                fetched_at=datetime.now(UTC),
            )
        )
    session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


def _propose_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Candidate A",
        "config": {
            "weights": {"trend": 1, "momentum": 1, "macd": 1, "bollinger": 1},
            "rsi_bullish_low": 50,
            "rsi_bullish_high": 70,
            "rsi_oversold": 30,
        },
    }
    body.update(overrides)
    return body


def _params_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "date_range_start": D0.isoformat(),
        "date_range_end": D_END.isoformat(),
        "benchmark_ticker": None,
    }
    body.update(overrides)
    return body


class TestPropose:
    def test_happy_path_creates_a_proposed_version(self, client: TestClient) -> None:
        response = client.post("/api/v1/strategy-versions", json=_propose_body())
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "PROPOSED"
        assert body["decided_at"] is None
        assert body["name"] == "Candidate A"

    def test_invalid_rsi_band_is_a_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/strategy-versions",
            json=_propose_body(
                config={
                    "weights": {"trend": 1, "momentum": 1, "macd": 1, "bollinger": 1},
                    "rsi_bullish_low": 70,
                    "rsi_bullish_high": 50,
                    "rsi_oversold": 30,
                }
            ),
        )
        assert response.status_code == 422

    def test_does_not_touch_any_active_version(
        self, client: TestClient, db_session: Session
    ) -> None:
        client.post("/api/v1/strategy-versions", json=_propose_body())
        active_count = (
            db_session.query(StrategyVersion)
            .filter(StrategyVersion.status == StrategyVersionStatus.ACTIVE)
            .count()
        )
        assert active_count == 0


class TestCompare:
    def test_persists_two_backtest_runs_without_changing_candidate_status(
        self, client: TestClient, db_session: Session
    ) -> None:
        candidate_id = client.post("/api/v1/strategy-versions", json=_propose_body()).json()["id"]

        response = client.post(
            f"/api/v1/strategy-versions/{candidate_id}/compare", json=_params_body()
        )

        assert response.status_code == 200
        body = response.json()
        assert "candidate_backtest" in body
        assert "active_backtest" in body
        assert "delta" in body
        assert body["candidate_backtest"]["strategy_version_id"] == candidate_id

        assert db_session.query(BacktestRun).count() == 2

        candidate = db_session.get(StrategyVersion, candidate_id)
        assert candidate is not None
        assert candidate.status == StrategyVersionStatus.PROPOSED

    def test_unknown_id_404s(self, client: TestClient) -> None:
        response = client.post("/api/v1/strategy-versions/999999/compare", json=_params_body())
        assert response.status_code == 404


class TestApprove:
    def test_happy_path_activates_candidate_and_supersedes_previous_active(
        self, client: TestClient, db_session: Session
    ) -> None:
        candidate_id = client.post("/api/v1/strategy-versions", json=_propose_body()).json()["id"]

        response = client.post(
            f"/api/v1/strategy-versions/{candidate_id}/approve",
            json=_params_body(comment="looks good"),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ACTIVE"
        assert body["decided_at"] is not None
        assert body["decision_comment"] == "looks good"

        rows = (
            db_session.execute(select(StrategyVersion).order_by(StrategyVersion.id)).scalars().all()
        )
        statuses = {r.id: r.status for r in rows}
        assert statuses[candidate_id] == StrategyVersionStatus.ACTIVE
        superseded = [r for r in rows if r.status == StrategyVersionStatus.SUPERSEDED]
        assert len(superseded) == 1

        audit_rows = (
            db_session.execute(
                select(AuditEvent).where(AuditEvent.record_type == "STRATEGY_VERSION_APPROVED")
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        snapshot = audit_rows[0].snapshot
        assert snapshot["previous_active_strategy_version_id"] == superseded[0].id
        assert "candidate_backtest_run_id" in snapshot
        assert "active_backtest_run_id" in snapshot

    def test_approving_a_non_proposed_version_is_a_400(self, client: TestClient) -> None:
        candidate_id = client.post("/api/v1/strategy-versions", json=_propose_body()).json()["id"]
        client.post(f"/api/v1/strategy-versions/{candidate_id}/approve", json=_params_body())

        second_response = client.post(
            f"/api/v1/strategy-versions/{candidate_id}/approve", json=_params_body()
        )
        assert second_response.status_code == 400

    def test_unknown_id_404s(self, client: TestClient) -> None:
        response = client.post("/api/v1/strategy-versions/999999/approve", json=_params_body())
        assert response.status_code == 404


class TestReject:
    def test_happy_path_rejects_without_touching_active_version(
        self, client: TestClient, db_session: Session
    ) -> None:
        candidate_id = client.post("/api/v1/strategy-versions", json=_propose_body()).json()["id"]

        response = client.post(
            f"/api/v1/strategy-versions/{candidate_id}/reject", json={"comment": "not this one"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["decided_at"] is not None
        assert body["decision_comment"] == "not this one"

        assert db_session.query(BacktestRun).count() == 0
        active_count = (
            db_session.query(StrategyVersion)
            .filter(StrategyVersion.status == StrategyVersionStatus.ACTIVE)
            .count()
        )
        assert active_count == 0

        audit_rows = (
            db_session.execute(
                select(AuditEvent).where(AuditEvent.record_type == "STRATEGY_VERSION_REJECTED")
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1

    def test_rejecting_a_non_proposed_version_is_a_400(self, client: TestClient) -> None:
        candidate_id = client.post("/api/v1/strategy-versions", json=_propose_body()).json()["id"]
        client.post(f"/api/v1/strategy-versions/{candidate_id}/reject", json={})

        second_response = client.post(f"/api/v1/strategy-versions/{candidate_id}/reject", json={})
        assert second_response.status_code == 400


class TestListAndGet:
    def test_list_and_get_roundtrip(self, client: TestClient) -> None:
        created = client.post("/api/v1/strategy-versions", json=_propose_body()).json()

        list_response = client.get("/api/v1/strategy-versions")
        assert list_response.status_code == 200
        assert any(v["id"] == created["id"] for v in list_response.json())

        get_response = client.get(f"/api/v1/strategy-versions/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == created["id"]

    def test_unknown_id_404s(self, client: TestClient) -> None:
        response = client.get("/api/v1/strategy-versions/999999")
        assert response.status_code == 404
