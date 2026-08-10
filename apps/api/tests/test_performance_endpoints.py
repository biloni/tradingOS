"""Performance router smoke tests (Revision Prompt 12) — every new
endpoint returns a 200 with a well-formed body against real seeded/
fresh-account state; deep formula correctness is already covered by
`test_performance_metrics.py`/`test_performance_portfolio.py`/etc."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tradingos_api.models.execution import Account


class TestPortfolioAndStrategyEndpoints:
    def test_portfolio_performance_view(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(f"/api/v1/performance/portfolio/{fresh_account.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["equity"] is not None

    def test_portfolio_performance_unknown_account_is_404(self, client: TestClient) -> None:
        import uuid

        response = client.get(f"/api/v1/performance/portfolio/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_lane_contribution_view(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(f"/api/v1/performance/strategy/{fresh_account.id}/lane-contribution")
        assert response.status_code == 200
        assert response.json() == []

    def test_policy_veto_outcomes_view(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(f"/api/v1/performance/strategy/{fresh_account.id}/policy-vetoes")
        assert response.status_code == 200
        assert response.json()["total_evaluations"] >= 0


class TestRecommendationAndMorningPlanEndpoints:
    def test_recommendation_reality_view(self, client: TestClient) -> None:
        response = client.get("/api/v1/performance/recommendations/reality")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_morning_plan_quality_view(self, client: TestClient) -> None:
        response = client.get("/api/v1/performance/morning-plan/quality")
        assert response.status_code == 200
        assert "total_runs" in response.json()

    def test_approval_conversion_view(self, client: TestClient) -> None:
        response = client.get("/api/v1/performance/morning-plan/approval-conversion")
        assert response.status_code == 200


class TestCoachEndpoint:
    def test_coach_summary_fresh_account_is_inadequate_sample(
        self, client: TestClient, fresh_account: Account
    ) -> None:
        """A fresh account has zero closed trades — this must return 200
        with `is_sample_adequate: false` and no `ANTHROPIC_API_KEY`
        required, never a 503, since the LLM is never reached."""
        response = client.get(f"/api/v1/performance/coach/{fresh_account.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["is_sample_adequate"] is False
        assert body["sample_size"] == 0
        assert body["narrative"] is None

    def test_coach_summary_unknown_account_is_404(self, client: TestClient) -> None:
        import uuid

        response = client.get(f"/api/v1/performance/coach/{uuid.uuid4()}")
        assert response.status_code == 404


class TestChartEndpoints:
    def test_equity_curve_chart(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(f"/api/v1/performance/charts/equity-curve/{fresh_account.id}")
        assert response.status_code == 200
        assert "account_points" in response.json()

    def test_drawdown_chart(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(f"/api/v1/performance/charts/drawdown/{fresh_account.id}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_score_threshold_sensitivity_chart(
        self, client: TestClient, fresh_account: Account
    ) -> None:
        response = client.get(
            f"/api/v1/performance/charts/score-threshold-sensitivity/{fresh_account.id}"
        )
        assert response.status_code == 200
        thresholds = [p["score_threshold"] for p in response.json()]
        assert thresholds == [4, 5, 6, 7]

    def test_calibration_chart(self, client: TestClient) -> None:
        response = client.get("/api/v1/performance/charts/calibration")
        assert response.status_code == 200
        body = response.json()
        assert "LOW" in body and "MEDIUM" in body and "HIGH" in body

    def test_morning_recommendation_funnel_chart(self, client: TestClient) -> None:
        response = client.get("/api/v1/performance/charts/morning-recommendation-funnel")
        assert response.status_code == 200
        body = response.json()
        assert body["approvals_granted"] <= body["approvals_requested"]
