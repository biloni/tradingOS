"""Change governance tests (Revision Prompt 14) — the state machine
structurally prevents self-activation, activation/rollback never rewrite
`RecommendationVersion` history, and version comparison (current vs.
proposed) is captured exactly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    EventBacktestStrategyKey,
    ModelChangeProposalStatus,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    RecommendationStatus,
    StrategyVersionStatus,
)
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.learning import StrategyDefinition, StrategyVersion
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.backtest_engine import BacktestRunConfig
from tradingos_api.services.change_governance import (
    ProposalNotFoundError,
    activate_change,
    approve_change,
    propose_strategy_parameter_change,
    reject_change,
    rollback_change,
    withdraw_change,
)
from tradingos_api.services.lifecycle import InvalidTransitionError

_NARROW_CONFIG_KWARGS = {
    "start": datetime(2026, 2, 1, tzinfo=UTC).date(),
    "end": datetime(2026, 7, 31, tzinfo=UTC).date(),
    "universe_start": datetime(2024, 8, 1, tzinfo=UTC).date(),
    "universe_end": datetime(2026, 7, 31, tzinfo=UTC).date(),
}


def _strategy_definition(db: Session, user: UserProfile) -> StrategyDefinition:
    sd = StrategyDefinition(name="Test governance strategy", owner_user_id=user.id)
    db.add(sd)
    db.flush()
    return sd


def _propose(db: Session, user: UserProfile, sd: StrategyDefinition):
    current = BacktestRunConfig(
        strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
        score_threshold=5,
        **_NARROW_CONFIG_KWARGS,
    )
    proposed = BacktestRunConfig(
        strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
        score_threshold=6,
        **_NARROW_CONFIG_KWARGS,
    )
    return propose_strategy_parameter_change(
        db,
        owner_user_id=user.id,
        strategy_definition_id=sd.id,
        current_config=current,
        proposed_config=proposed,
        economic_rationale="Test rationale",
        costs={"engineering_hours": 1},
        operational_risks=["fewer signals"],
        rollback_plan="Reactivate score_threshold=5",
        description="Raise score threshold from 5 to 6",
    )


class TestNoSelfActivation:
    def test_cannot_activate_a_proposed_proposal_directly(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        assert proposal.status == ModelChangeProposalStatus.PROPOSED

        try:
            activate_change(db_session, proposal_id=proposal.id, activated_by="ops")
            raise AssertionError("activation from PROPOSED must be rejected")
        except InvalidTransitionError:
            pass

        db_session.refresh(proposal)
        assert proposal.status == ModelChangeProposalStatus.PROPOSED

    def test_cannot_rollback_before_activation(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        approve_change(db_session, proposal_id=proposal.id, decided_by="cro")
        try:
            rollback_change(
                db_session, proposal_id=proposal.id, rolled_back_by="cro", reason="too soon"
            )
            raise AssertionError("rollback before activation must be rejected")
        except InvalidTransitionError:
            pass


class TestStateMachine:
    def test_full_propose_approve_activate_rollback_lifecycle(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)

        approved = approve_change(db_session, proposal_id=proposal.id, decided_by="cro")
        assert approved.status == ModelChangeProposalStatus.APPROVED

        activated = activate_change(db_session, proposal_id=proposal.id, activated_by="cro")
        assert activated.status == ModelChangeProposalStatus.ACTIVATED
        assert activated.activated_by == "cro"

        candidate = db_session.get(StrategyVersion, proposal.subject_ref_id)
        assert candidate is not None
        assert candidate.status == StrategyVersionStatus.ACTIVE

        rolled_back = rollback_change(
            db_session, proposal_id=proposal.id, rolled_back_by="cro", reason="regression"
        )
        assert rolled_back.status == ModelChangeProposalStatus.ROLLED_BACK

        db_session.refresh(candidate)
        assert candidate.status == StrategyVersionStatus.SUPERSEDED

        active_versions = db_session.scalars(
            select(StrategyVersion).where(
                StrategyVersion.strategy_definition_id == sd.id,
                StrategyVersion.status == StrategyVersionStatus.ACTIVE,
            )
        ).all()
        assert len(active_versions) == 1
        assert active_versions[0].config["score_threshold"] == 5

    def test_reject_is_terminal(self, db_session: Session, seeded_user_id: uuid.UUID) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        rejected = reject_change(
            db_session, proposal_id=proposal.id, decided_by="cro", comment="not now"
        )
        assert rejected.status == ModelChangeProposalStatus.REJECTED
        try:
            approve_change(db_session, proposal_id=proposal.id, decided_by="cro")
            raise AssertionError("approving a rejected proposal must fail")
        except InvalidTransitionError:
            pass

    def test_withdraw_from_proposed(self, db_session: Session, seeded_user_id: uuid.UUID) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        withdrawn = withdraw_change(db_session, proposal_id=proposal.id)
        assert withdrawn.status == ModelChangeProposalStatus.WITHDRAWN

    def test_unknown_proposal_id_raises(self, db_session: Session) -> None:
        try:
            approve_change(db_session, proposal_id=uuid.uuid4(), decided_by="cro")
            raise AssertionError("unknown proposal must raise")
        except ProposalNotFoundError:
            pass


class TestVersionComparison:
    def test_current_and_proposed_snapshots_match_the_input_configs(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        current_snapshot = proposal.evidence_package["current_version_snapshot"]
        proposed_snapshot = proposal.evidence_package["proposed_version_snapshot"]
        assert current_snapshot["score_threshold"] == 5
        assert proposed_snapshot["score_threshold"] == 6
        assert current_snapshot["strategy_key"] == "SCORED_PRE_EARNINGS_BASELINE"

    def test_evidence_package_contains_all_required_sections(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        required_keys = {
            "sample_size", "evidence", "current_version_snapshot",
            "proposed_version_snapshot", "economic_rationale", "train_results",
            "validation_results", "out_of_sample_results", "walk_forward_results",
            "sensitivity", "costs", "operational_risks", "rollback_plan",
        }  # fmt: skip
        assert required_keys.issubset(proposal.evidence_package.keys())


class TestNeverRewritesHistoricalRecommendations:
    def test_recommendation_version_unchanged_across_full_lifecycle(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        user = db_session.get(UserProfile, seeded_user_id)
        assert user is not None
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None

        recommendation = Recommendation(
            instrument_id=amd.id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db_session.add(recommendation)
        db_session.flush()
        version = RecommendationVersion(
            recommendation_id=recommendation.id,
            version_number=1,
            action=RecommendationAction.BUY,
            confidence=RecommendationConfidence.MEDIUM,
            score=Decimal("6.5"),
            rationale="Pre-existing recommendation, must survive unchanged.",
            generated_at=datetime.now(UTC),
        )
        db_session.add(version)
        db_session.flush()

        before = {
            "action": version.action,
            "confidence": version.confidence,
            "score": version.score,
            "rationale": version.rationale,
            "generated_at": version.generated_at,
        }

        sd = _strategy_definition(db_session, user)
        proposal = _propose(db_session, user, sd)
        approve_change(db_session, proposal_id=proposal.id, decided_by="cro")
        activate_change(db_session, proposal_id=proposal.id, activated_by="cro")
        rollback_change(
            db_session, proposal_id=proposal.id, rolled_back_by="cro", reason="test"
        )

        db_session.refresh(version)
        after = {
            "action": version.action,
            "confidence": version.confidence,
            "score": version.score,
            "rationale": version.rationale,
            "generated_at": version.generated_at,
        }
        assert before == after
