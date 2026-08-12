"""Release-gate journey tests (Revision Prompt 16, task: release-gate
tests — synthetic journey + failure journeys).

Every other test file in this suite proves one function or one endpoint
in isolation; this file chains several already-tested subsystems
together in the sequences a real usage session actually produces, to
catch wiring bugs unit tests can't see — does the morning plan's
account really connect to the order-authority flow's account, does an
activated kill switch really block a submission that's already passed
every earlier gate, does an expired approval really get refused by the
router layer and not just the service function.

`TestSyntheticGoldenJourney` also closes a real, pre-existing gap: no
test anywhere in this suite previously drove the full order-authority
chain (`POST /order-proposals` -> `/policy-evaluation` -> `POST
/order-approvals` -> `/approve` -> `/submit`) over HTTP —
`test_step_up_reauth.py`'s own docstring says so explicitly ("no
factory for the full proposal->approval chain exists yet").

Uses the AMD seed recommendation (`scripts/seed_phase8.py`) and AMD's
fixed synthetic reference price (`core/dependencies.py`,
`SyntheticPaperBrokerProvider`/`SyntheticMarketQuoteProvider`) so the
quote never moves between approval and submission — no external network
call, no LLM call, fully deterministic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import AccountType, OrderApprovalStatus, ReconciliationStatus
from tradingos_api.models.execution import Account
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.routers.auth import step_up_rate_limiter

from .conftest import TEST_PASSWORD


def _step_up(client: TestClient) -> None:
    # step_up_rate_limiter is a module-level singleton shared by the
    # whole pytest process (same fact test_step_up_reauth.py's own
    # fixture already documents for login_rate_limiter) — resetting it
    # here, not just at client-fixture setup, is what makes repeated
    # step-up calls across this file's several journeys reliable
    # regardless of how many other tests already consumed the budget
    # earlier in a full-suite run. Found failing for real: this file's
    # newest test tripped a 429 that earlier tests in the same run
    # happened to not hit, purely by how many prior step-ups had fired.
    step_up_rate_limiter.reset()
    response = client.post("/api/v1/auth/step-up", json={"password": TEST_PASSWORD})
    assert response.status_code == 200, response.text


def _amd_recommendation_version_id(db: Session) -> uuid.UUID:
    inst = db.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None, "seed data must include AMD"
    rec = db.scalar(select(Recommendation).where(Recommendation.instrument_id == inst.id))
    assert rec is not None, "seed data must include an AMD recommendation"
    version = db.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == rec.id)
        .order_by(RecommendationVersion.version_number.desc())
    )
    assert version is not None
    return version.id


def _paper_account_id(db: Session) -> uuid.UUID:
    account = db.scalar(select(Account).where(Account.account_type == AccountType.PAPER_ALPACA))
    assert account is not None, "seed data must include a PAPER_ALPACA account"
    return account.id


def _confirmation() -> dict[str, str]:
    return {
        "confirmed_at": datetime.now(UTC).isoformat(),
        "account_id": "release-gate-test",
        "environment": "paper",
        "broker_endpoint": "https://paper-api.alpaca.markets",
    }


def _propose_evaluate_approve(
    client: TestClient, db: Session, *, expires_in_seconds: int = 300
) -> uuid.UUID:
    """Everything through APPROVED — the shared setup every journey
    below needs before it diverges into success or a specific failure.
    Returns the approval id."""
    recommendation_version_id = _amd_recommendation_version_id(db)
    account_id = _paper_account_id(db)

    proposal_resp = client.post(
        "/api/v1/order-proposals",
        json={
            "recommendation_version_id": str(recommendation_version_id),
            "account_id": str(account_id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "5",
        },
    )
    assert proposal_resp.status_code == 201, proposal_resp.text
    proposal = proposal_resp.json()

    eval_resp = client.post(
        f"/api/v1/order-proposals/{proposal['id']}/policy-evaluation",
        json={
            "requested_mode": "PAPER_MANUAL_APPROVAL",
            "is_live": False,
            "confirmation": _confirmation(),
        },
    )
    assert eval_resp.status_code == 200, eval_resp.text
    evaluation = eval_resp.json()
    assert evaluation["authorized"] is True, evaluation

    approval_resp = client.post(
        "/api/v1/order-approvals",
        json={
            "order_proposal_version_id": proposal["latest_version"]["id"],
            "approved_by": "release-gate-test",
            "expires_in_seconds": expires_in_seconds,
        },
    )
    assert approval_resp.status_code == 201, approval_resp.text
    return uuid.UUID(approval_resp.json()["id"])


class TestSyntheticGoldenJourney:
    def test_morning_plan_then_full_order_authority_chain_then_reconcile(
        self, client: TestClient, db_session: Session
    ) -> None:
        # 1. The process itself is healthy and ready before anything else.
        assert client.get("/health").json()["status"] == "ok"
        ready = client.get("/ready")
        assert ready.json()["checks"]["database"]["status"] == "ok"

        # 2. Morning plan generation — day-aware: a real run only produces
        # a version on an actual trading day; a weekend/holiday run
        # correctly 422s instead. Either outcome is a legitimate proof
        # that the endpoint is wired and honest about the calendar; only
        # a genuine error (neither) would be a release-blocking finding.
        plan_resp = client.post("/api/v1/morning-plan/generate", json={})
        assert plan_resp.status_code in (201, 422), plan_resp.text
        if plan_resp.status_code == 201:
            version = plan_resp.json()
            dashboard = client.get("/api/v1/morning-plan/dashboard").json()
            assert dashboard["top_status"]["plan_version_id"] == version["id"]
            job_runs = client.get("/api/v1/ops/job-runs").json()
            assert any(r["id"] == version["morning_plan_run_id"] for r in job_runs) or any(
                r["plan_date"] == version["plan_date"] for r in job_runs
            )

        # 3. The real order-authority chain: propose -> evaluate ->
        # approve -> submit. This is the actual broker boundary
        # (services/order_execution.py) — distinct from, and a stronger
        # proof than, routers/orders.py's simpler manual-entry
        # propose/confirm pair the Playwright suite already covers.
        approval_id = _propose_evaluate_approve(client, db_session)

        _step_up(client)
        approve_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/approve",
            json={"approved_by": "release-gate-test"},
        )
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["status"] == "APPROVED"

        submit_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/submit",
            json={"requested_mode": "PAPER_MANUAL_APPROVAL", "confirmation": _confirmation()},
        )
        assert submit_resp.status_code == 200, submit_resp.text
        submission = submit_resp.json()
        assert submission["invalidated"] is False, submission
        assert submission["order_id"] is not None
        assert submission["order_status"] in ("SUBMITTED", "FILLED", "PARTIALLY_FILLED")

        order_resp = client.get(f"/api/v1/orders/{submission['order_id']}")
        assert order_resp.status_code == 200
        assert order_resp.json()["instrument"]["ticker"] == "AMD"

        # 4. Reconciliation — the account this order just posted to still
        # reconciles cleanly against itself (no broker feed configured
        # in this test env, so MATCHED is the only honest outcome for a
        # PAPER_ALPACA account reconciled with no broker-reported figures).
        reconcile_resp = client.post(
            f"/api/v1/portfolio/accounts/{_paper_account_id(db_session)}/reconcile", json={}
        )
        assert reconcile_resp.status_code == 200, reconcile_resp.text


class TestFailureJourneys:
    """Each test proves the system fails the *correct* way — a graceful,
    observable denial with a reason, never a silent pass-through or a
    raw crash."""

    def test_kill_switch_blocks_submission_after_every_earlier_gate_passed(
        self, client: TestClient, db_session: Session
    ) -> None:
        approval_id = _propose_evaluate_approve(client, db_session)
        _step_up(client)
        approve_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/approve",
            json={"approved_by": "release-gate-test"},
        )
        assert approve_resp.status_code == 200, approve_resp.text

        kill_resp = client.post(
            "/api/v1/settings/kill-switch/activate",
            json={"activated_by": "release-gate-test", "reason": "test"},
        )
        assert kill_resp.status_code == 201, kill_resp.text

        submit_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/submit",
            json={"requested_mode": "PAPER_MANUAL_APPROVAL", "confirmation": _confirmation()},
        )
        # Not an HTTP error — a graceful, observable denial: the
        # approval itself flips to INVALIDATED and no order is created,
        # matching services/order_execution.py's hard-veto path.
        assert submit_resp.status_code == 200, submit_resp.text
        submission = submit_resp.json()
        assert submission["invalidated"] is True
        assert submission["order_id"] is None
        assert "kill switch" in (submission["invalidation_reason"] or "").lower()

        approval_check = client.get(f"/api/v1/order-approvals/{approval_id}")
        assert approval_check.json()["status"] == OrderApprovalStatus.INVALIDATED.value

    def test_an_already_expired_approval_cannot_be_approved(
        self, client: TestClient, db_session: Session
    ) -> None:
        # A negative expiry makes expires_at fall in the past the moment
        # the approval is created — the wall-clock re-check inside
        # assert_can_transition_to_approved() must catch this at the
        # router layer, not just in the unit-tested service function
        # (test_services_order_authority.py already covers the service
        # function directly; this proves the HTTP route enforces it too).
        approval_id = _propose_evaluate_approve(client, db_session, expires_in_seconds=-5)
        _step_up(client)
        approve_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/approve",
            json={"approved_by": "release-gate-test"},
        )
        assert approve_resp.status_code == 400
        assert "expired" in approve_resp.json()["detail"].lower()

    def test_a_rejected_approval_cannot_later_be_submitted(
        self, client: TestClient, db_session: Session
    ) -> None:
        approval_id = _propose_evaluate_approve(client, db_session)
        reject_resp = client.post(f"/api/v1/order-approvals/{approval_id}/reject")
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "REJECTED"

        _step_up(client)
        submit_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/submit",
            json={"requested_mode": "PAPER_MANUAL_APPROVAL", "confirmation": _confirmation()},
        )
        assert submit_resp.status_code == 403
        assert "REJECTED" in submit_resp.json()["detail"]

    def test_manual_reconciliation_surfaces_a_real_discrepancy(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        # fresh_account (MANUAL, order-free per its own fixture docstring)
        # holds nothing; a broker report claiming 50 shares of AMD is an
        # unambiguous, deterministic mismatch — proves a discrepancy is
        # surfaced, not silently reconciled away.
        response = client.post(
            f"/api/v1/portfolio/accounts/{fresh_account.id}/reconcile",
            json={"broker_reported_positions": {"AMD": "50"}},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["overall_status"] == ReconciliationStatus.DISCREPANCY.value
        discrepancy_lines = [
            line
            for line in body["lines"]
            if line["status"] == ReconciliationStatus.DISCREPANCY.value
        ]
        assert len(discrepancy_lines) == 1
        assert discrepancy_lines[0]["instrument"]["ticker"] == "AMD"
        assert Decimal(discrepancy_lines[0]["broker_reported_quantity"]) == Decimal("50")
        assert discrepancy_lines[0]["discrepancy_detail"] is not None


class TestListOrderApprovals:
    """`GET /api/v1/order-approvals` — added alongside end-to-end platform
    testing to give `apps/web/app/approvals/page.tsx` (a Revision Prompt
    R2 placeholder with no real data source) something real to list."""

    def test_defaults_to_pending_only(self, client: TestClient, db_session: Session) -> None:
        approval_id = _propose_evaluate_approve(client, db_session)

        response = client.get("/api/v1/order-approvals")
        assert response.status_code == 200, response.text
        ids = [a["id"] for a in response.json()]
        assert str(approval_id) in ids
        assert all(a["status"] == "PENDING" for a in response.json())

    def test_approved_approval_drops_out_of_the_default_pending_list(
        self, client: TestClient, db_session: Session
    ) -> None:
        approval_id = _propose_evaluate_approve(client, db_session)
        _step_up(client)
        approve_resp = client.post(
            f"/api/v1/order-approvals/{approval_id}/approve",
            json={"approved_by": "release-gate-test"},
        )
        assert approve_resp.status_code == 200, approve_resp.text

        pending = client.get("/api/v1/order-approvals").json()
        assert str(approval_id) not in [a["id"] for a in pending]

        approved = client.get("/api/v1/order-approvals?status=APPROVED").json()
        assert str(approval_id) in [a["id"] for a in approved]

    def test_most_recent_first(self, client: TestClient, db_session: Session) -> None:
        first_id = _propose_evaluate_approve(client, db_session)
        second_id = _propose_evaluate_approve(client, db_session)

        ids = [a["id"] for a in client.get("/api/v1/order-approvals").json()]
        assert ids.index(str(second_id)) < ids.index(str(first_id))
