"""Revision Prompt R3's required tests that are cross-cutting rather
than belonging to one router/model: existing API clients remain
compatible, and investment/tactical recommendations cannot be confused.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.main import app
from tradingos_api.models.enums import RecommendationAction, RecommendationConfidence
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion

_unauthenticated_client = TestClient(app)

# Every path/method pair that existed before Revision Prompt R3 (captured
# from tests/fixtures/openapi_paths_snapshot.json prior to this
# revision's endpoint additions) — R3 adds routes but must never remove
# or reshape one of these.
PRE_R3_PATHS: list[tuple[str, list[str]]] = [
    ("/api/v1/alerts", ["get"]),
    ("/api/v1/alerts/{alert_id}", ["patch"]),
    ("/api/v1/backtests", ["get"]),
    ("/api/v1/backtests/{run_id}", ["get"]),
    ("/api/v1/instruments", ["get"]),
    ("/api/v1/instruments/validate", ["post"]),
    ("/api/v1/instruments/{instrument_id}", ["get"]),
    ("/api/v1/instruments/{instrument_id}/validation-events", ["get"]),
    ("/api/v1/journal/trades", ["get"]),
    ("/api/v1/journal/trades/{trade_id}", ["get"]),
    ("/api/v1/journal/trades/{trade_id}/notes", ["post"]),
    ("/api/v1/journal/trades/{trade_id}/reviews", ["post"]),
    ("/api/v1/market/freshness", ["get"]),
    ("/api/v1/market/instruments/{ticker}/bars", ["get"]),
    ("/api/v1/market/instruments/{ticker}/indicators", ["get"]),
    ("/api/v1/market/overview", ["get"]),
    ("/api/v1/orders", ["get", "post"]),
    ("/api/v1/orders/import", ["post"]),
    ("/api/v1/orders/reconciliation/{account_id}", ["get"]),
    ("/api/v1/orders/{order_id}", ["get"]),
    ("/api/v1/orders/{order_id}/cancel", ["post"]),
    ("/api/v1/orders/{order_id}/confirm", ["post"]),
    ("/api/v1/performance/accounts/{account_id}", ["get"]),
    ("/api/v1/performance/compare/{account_id}", ["get"]),
    ("/api/v1/plans/daily", ["get"]),
    ("/api/v1/portfolio/accounts", ["get"]),
    ("/api/v1/portfolio/accounts/{account_id}", ["get"]),
    ("/api/v1/recommendations", ["get"]),
    ("/api/v1/recommendations/committee-sessions/{session_id}", ["get"]),
    ("/api/v1/recommendations/{recommendation_id}", ["get"]),
    ("/api/v1/settings/investment-profile", ["get"]),
    ("/api/v1/settings/operating-mode", ["get"]),
    ("/api/v1/settings/providers", ["get"]),
    ("/api/v1/settings/risk-policy", ["get", "patch"]),
    ("/api/v1/watchlists", ["get"]),
    ("/api/v1/watchlists/items/{item_id}", ["patch"]),
    ("/api/v1/watchlists/{watchlist_id}/items", ["get", "post"]),
    ("/health", ["get"]),
]


def test_every_pre_r3_path_and_method_still_present() -> None:
    spec = _unauthenticated_client.get("/openapi.json").json()
    actual = {path: sorted(methods.keys()) for path, methods in spec["paths"].items()}
    missing = [path for path, _ in PRE_R3_PATHS if path not in actual]
    assert not missing, f"R3 removed pre-existing routes: {missing}"
    for path, methods in PRE_R3_PATHS:
        assert actual[path] == methods, (
            f"{path} changed methods: expected {methods}, got {actual[path]}"
        )


def test_pre_r3_response_schema_unchanged() -> None:
    """A spot-check that R3 did not alter an existing response shape out
    from under an existing client — `OrderResponse` is the highest-risk
    one since R3 also introduces its own order-shaped schemas
    (`OrderProposalVersionResponse`, `ApprovalBoundFieldsResponse`) that
    must stay structurally distinct from it, not accidentally reused."""
    spec = _unauthenticated_client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "OrderResponse" in schemas
    order_fields = set(schemas["OrderResponse"]["properties"].keys())
    assert order_fields == {
        "id",
        "account_id",
        "instrument",
        "side",
        "order_type",
        "time_in_force",
        "quantity",
        "limit_price",
        "status",
        "submitted_at",
        "filled_at",
        "created_at",
        "executions",
    }


class TestInvestmentAndTacticalCannotBeConfused:
    """R3's required test: a recommendation's lane is unambiguous both
    in the DB (ADR-046's `mode` column) and at the API boundary (the two
    routers only ever return rows matching their own lane, 404ing on a
    cross-lane id lookup rather than silently returning it)."""

    def _make_recommendation(
        self, db_session: Session, *, mode: str, instrument_id: uuid.UUID
    ) -> Recommendation:
        rec = Recommendation(
            instrument_id=instrument_id,
            mode=mode,
            opened_at=datetime.now(UTC),
        )
        db_session.add(rec)
        db_session.flush()
        db_session.add(
            RecommendationVersion(
                recommendation_id=rec.id,
                version_number=1,
                action=RecommendationAction.HOLD,
                confidence=RecommendationConfidence.MEDIUM,
                rationale="test fixture",
                generated_at=datetime.now(UTC),
                deterministic_inputs_snapshot={},
            )
        )
        db_session.flush()
        return rec

    def test_tactical_endpoint_404s_on_an_investment_id(
        self, client: TestClient, db_session: Session, seeded_instrument_id: uuid.UUID
    ) -> None:
        rec = self._make_recommendation(
            db_session, mode="INVESTMENT", instrument_id=seeded_instrument_id
        )
        response = client.get(f"/api/v1/tactical/recommendations/{rec.id}")
        assert response.status_code == 404

    def test_investment_endpoint_404s_on_a_tactical_id(
        self, client: TestClient, db_session: Session, seeded_instrument_id: uuid.UUID
    ) -> None:
        rec = self._make_recommendation(
            db_session, mode="TACTICAL", instrument_id=seeded_instrument_id
        )
        response = client.get(f"/api/v1/investment/recommendations/{rec.id}")
        assert response.status_code == 404

    def test_investment_list_excludes_tactical_rows(
        self, client: TestClient, db_session: Session, seeded_instrument_id: uuid.UUID
    ) -> None:
        tactical = self._make_recommendation(
            db_session, mode="TACTICAL", instrument_id=seeded_instrument_id
        )
        response = client.get("/api/v1/investment/recommendations", params={"limit": 200})
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()["items"]}
        assert str(tactical.id) not in ids

    def test_tactical_list_excludes_investment_rows(
        self, client: TestClient, db_session: Session, seeded_instrument_id: uuid.UUID
    ) -> None:
        investment = self._make_recommendation(
            db_session, mode="INVESTMENT", instrument_id=seeded_instrument_id
        )
        response = client.get("/api/v1/tactical/recommendations", params={"limit": 200})
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()["items"]}
        assert str(investment.id) not in ids
