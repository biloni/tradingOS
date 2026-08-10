"""Governance router smoke tests (Revision Prompt 14) — calibration,
agent evaluation, and the full proposal lifecycle against real Postgres
state via the FastAPI `TestClient`."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.models.identity import UserProfile
from tradingos_api.models.learning import StrategyDefinition


def _strategy_definition_id(db_session: Session, user: UserProfile) -> str:
    sd = StrategyDefinition(name=f"Endpoint test {uuid.uuid4()}", owner_user_id=user.id)
    db_session.add(sd)
    db_session.flush()
    db_session.commit()
    return str(sd.id)


class TestCalibrationEndpoint:
    def test_valid_axis_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/calibration", params={"axis": "confidence"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_invalid_axis_is_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/calibration", params={"axis": "bogus"})
        assert response.status_code == 422

    def test_every_required_axis_is_supported(self, client: TestClient) -> None:
        for axis in (
            "confidence", "score", "strategy", "sector", "regime",
            "event_timing", "holding_period",
        ):  # fmt: skip
            response = client.get("/api/v1/governance/calibration", params={"axis": axis})
            assert response.status_code == 200, axis


class TestAgentEvaluationEndpoint:
    def test_single_role(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/agent-evaluation/TACTICAL_BULL")
        assert response.status_code == 200
        body = response.json()
        assert body["agent_role"] == "TACTICAL_BULL"
        assert "sample_size" in body

    def test_all_roles(self, client: TestClient) -> None:
        response = client.get("/api/v1/governance/agent-evaluation")
        assert response.status_code == 200
        assert len(response.json()) == 25


class TestProposalLifecycle:
    def test_full_lifecycle_via_api(
        self, client: TestClient, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        strategy_definition_id = _strategy_definition_id(db_session, user)

        created = client.post(
            "/api/v1/governance/proposals/strategy-parameter",
            json={
                "strategy_definition_id": strategy_definition_id,
                "strategy_key": "SCORED_PRE_EARNINGS_BASELINE",
                "current_score_threshold": 5,
                "proposed_score_threshold": 6,
                "economic_rationale": "test",
                "costs": {},
                "operational_risks": [],
                "rollback_plan": "revert",
                "description": "test proposal",
            },
        )
        assert created.status_code == 201, created.text
        proposal_id = created.json()["id"]
        assert created.json()["status"] == "PROPOSED"

        premature_activate = client.post(
            f"/api/v1/governance/proposals/{proposal_id}/activate", json={"activated_by": "ops"}
        )
        assert premature_activate.status_code == 409

        approved = client.post(
            f"/api/v1/governance/proposals/{proposal_id}/approve",
            json={"decided_by": "cro", "comment": "ok"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"

        activated = client.post(
            f"/api/v1/governance/proposals/{proposal_id}/activate", json={"activated_by": "cro"}
        )
        assert activated.status_code == 200
        assert activated.json()["status"] == "ACTIVATED"

        rolled_back = client.post(
            f"/api/v1/governance/proposals/{proposal_id}/rollback",
            json={"rolled_back_by": "cro", "reason": "test rollback"},
        )
        assert rolled_back.status_code == 200
        assert rolled_back.json()["status"] == "ROLLED_BACK"

        detail = client.get(f"/api/v1/governance/proposals/{proposal_id}")
        assert detail.status_code == 200
        assert len(detail.json()["approvals"]) == 1

    def test_unknown_strategy_definition_is_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/governance/proposals/strategy-parameter",
            json={
                "strategy_definition_id": str(uuid.uuid4()),
                "strategy_key": "SCORED_PRE_EARNINGS_BASELINE",
                "current_score_threshold": 5,
                "proposed_score_threshold": 6,
                "economic_rationale": "test",
                "costs": {},
                "operational_risks": [],
                "rollback_plan": "revert",
                "description": "test",
            },
        )
        assert response.status_code == 404

    def test_generic_proposal_requires_full_evidence_package(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/governance/proposals",
            json={
                "subject_type": "PROMPT",
                "description": "Bump the Bull analyst prompt version",
                "evidence_package": {"sample_size": 5},
            },
        )
        assert response.status_code == 422

    def test_unknown_proposal_actions_are_404(self, client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/governance/proposals/{fake_id}/approve",
            json={"decided_by": "cro"},
        )
        assert response.status_code == 404


class TestProposalListing:
    def test_list_and_detail(
        self, client: TestClient, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        strategy_definition_id = _strategy_definition_id(db_session, user)
        created = client.post(
            "/api/v1/governance/proposals/strategy-parameter",
            json={
                "strategy_definition_id": strategy_definition_id,
                "strategy_key": "SCORED_PRE_EARNINGS_BASELINE",
                "current_score_threshold": 5,
                "proposed_score_threshold": 7,
                "economic_rationale": "test",
                "costs": {},
                "operational_risks": [],
                "rollback_plan": "revert",
                "description": "list/detail test",
            },
        )
        proposal_id = created.json()["id"]
        listed = client.get("/api/v1/governance/proposals", params={"limit": 50})
        assert listed.status_code == 200
        assert any(item["id"] == proposal_id for item in listed.json()["items"])

    def test_unknown_proposal_detail_is_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/governance/proposals/{uuid.uuid4()}")
        assert response.status_code == 404
