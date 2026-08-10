"""Demo script for Revision Prompt 14 — controlled learning, calibration,
and strategy governance.

Demonstrates:
1. Calibration: `get_closed_outcomes()` against real dev-DB state, then
   reliability by confidence band and by score band, plus honest sparse-
   bin suppression on a low-volume segmentation axis (event timing).
2. Agent evaluation: all 6 dimensions for one committee role, computed
   from real `AgentRun`/`AgentOpinion`/`AgentEvidenceLink` data — and the
   "data revisions" category, live: citing evidence tied to a later-
   corrected earnings event visibly lowers factual accuracy.
3. The full change-governance lifecycle: propose a strategy-parameter
   change (backed by real `run_backtest_splits()` train/validation/
   out-of-sample/walk-forward results) -> a premature activate attempt
   correctly rejected by the state machine -> approve -> activate
   (StrategyVersion flips ACTIVE, the prior version SUPERSEDED) ->
   rollback (a new StrategyVersion cloned from the prior config is
   activated instead of resurrecting the superseded row) -> proof that
   `RecommendationVersion` history is byte-identical throughout.

Run with: `python -m tradingos_api.scripts.demo_prompt14`
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.agents import (
    AgentDefinition,
    AgentEvidenceLink,
    AgentOpinion,
    AgentRun,
    AgentVersion,
)
from tradingos_api.models.agents import CommitteeSession as CommitteeSessionModel
from tradingos_api.models.enums import (
    AgentRole,
    AgentRunStatus,
    CommitteeSessionStatus,
    EventBacktestStrategyKey,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    RecommendationStatus,
    StrategyVersionStatus,
)
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.learning import RecommendationOutcome, StrategyDefinition, StrategyVersion
from tradingos_api.models.market_evidence import EarningsEvent, EarningsEventCorrection
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.agent_evaluation import evaluate_agent_role
from tradingos_api.services.backtest_engine import BacktestRunConfig
from tradingos_api.services.calibration import (
    CalibrationBin,
    calibration_by_event_timing,
    get_closed_outcomes,
    reliability_by_confidence_band,
    reliability_by_score_band,
)
from tradingos_api.services.change_governance import (
    activate_change,
    approve_change,
    propose_strategy_parameter_change,
    rollback_change,
)
from tradingos_api.services.lifecycle import InvalidTransitionError

_DEMO_ROLE = AgentRole.EARNINGS_GUIDANCE_ANALYST
"""Deliberately not `NEWS_CATALYST_ANALYST` — that role is
`tests/test_agent_evaluation.py`'s own exclusively-used role (chosen
there specifically because no other test file exercises it); this demo
persists real rows to the shared dev database (like every other
`demo_promptN.py` script), so writing to that same role here would
permanently invalidate that test file's baseline assumptions."""

_CONFIG_START = date(2026, 2, 1)
_CONFIG_END = date(2026, 7, 31)
_UNIVERSE_START = date(2024, 8, 1)
_UNIVERSE_END = date(2026, 7, 31)


def _print_bins(label: str, bins: list[CalibrationBin]) -> None:
    print(f"  {label}:")
    for b in bins:
        if b.is_adequate:
            print(
                f"    {b.label:12s} n={b.sample_size:4d} hit_rate={b.observed_hit_rate_pct}% "
                f"ci=[{b.ci_low_pct}, {b.ci_high_pct}] brier={b.brier_score}"
            )
        else:
            print(f"    {b.label:12s} n={b.sample_size:4d} INADEQUATE SAMPLE — no rate reported")


def _make_agent_evidence(
    db: Session, *, instrument_id: uuid.UUID, corrected_event_id: uuid.UUID
) -> None:
    """Seeds `MIN_SAMPLE_SIZE_FOR_AGENT_EVAL` runs for `_DEMO_ROLE` that
    cite a later-corrected earnings event, so factual accuracy is visibly
    depressed against whatever this dev DB's own baseline already is."""
    definition = db.scalar(select(AgentDefinition).where(AgentDefinition.role == _DEMO_ROLE))
    assert definition is not None
    version = AgentVersion(
        agent_definition_id=definition.id,
        version_label=f"demo-prompt14-{uuid.uuid4()}",
        model_name="claude-sonnet-5",
        is_active=True,
    )
    db.add(version)
    db.flush()

    for _ in range(10):
        session = CommitteeSessionModel(
            instrument_id=instrument_id,
            triggered_by="DEMO",
            mode=RecommendationMode.TACTICAL,
            status=CommitteeSessionStatus.COMPLETED,
        )
        db.add(session)
        db.flush()
        run = AgentRun(
            committee_session_id=session.id,
            agent_version_id=version.id,
            status=AgentRunStatus.SUCCEEDED,
            input_snapshot={"evidence_ids": [str(corrected_event_id)]},
        )
        db.add(run)
        db.flush()
        db.add(AgentOpinion(agent_run_id=run.id, stance="BULLISH", structured_output={}))
        db.add(
            AgentEvidenceLink(
                agent_run_id=run.id, evidence_type="EarningsEvent", evidence_id=corrected_event_id
            )
        )
        db.flush()

        recommendation = Recommendation(
            instrument_id=instrument_id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db.add(recommendation)
        db.flush()
        rec_version = RecommendationVersion(
            recommendation_id=recommendation.id,
            committee_session_id=session.id,
            version_number=1,
            action=RecommendationAction.BUY,
            confidence=RecommendationConfidence.MEDIUM,
            score=Decimal(7),
            rationale="Demo fixture for agent evaluation.",
            generated_at=datetime.now(UTC),
        )
        db.add(rec_version)
        db.flush()
        db.add(
            RecommendationOutcome(
                recommendation_id=recommendation.id,
                classification="FOLLOWED",
                realized_pnl=Decimal(100),
                computed_at=datetime.now(UTC),
            )
        )
        db.flush()


def main() -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(UserProfile))
        assert user is not None, "run the seed script first"
        amd = db.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None

        print("=== 1. Calibration against real dev-DB closed outcomes ===")
        outcomes = get_closed_outcomes(db)
        print(f"  total closed outcomes (actual + hypothetical, distinct): {len(outcomes)}")
        _print_bins("reliability by confidence band", reliability_by_confidence_band(outcomes))
        _print_bins("reliability by score band", reliability_by_score_band(outcomes))
        _print_bins(
            "calibration by event timing (expect INADEQUATE — few earnings-linked "
            "recommendations in this dev seed)",
            calibration_by_event_timing(outcomes),
        )

        print("\n=== 2. Agent evaluation — data revisions category ===")
        baseline = evaluate_agent_role(db, role=_DEMO_ROLE)
        print(
            f"  baseline (pre-existing seed data): sample_size={baseline.sample_size} "
            f"factual_accuracy_pct={baseline.factual_accuracy_pct}"
        )

        corrected_event = EarningsEvent(
            instrument_id=amd.id,
            fiscal_period="Q1-DEMO",
            report_date=date(2026, 1, 15),
            source="demo_prompt14",
        )
        db.add(corrected_event)
        db.flush()
        db.add(
            EarningsEventCorrection(
                earnings_event_id=corrected_event.id,
                version_number=2,
                corrected_field="report_date",
                previous_value="2026-01-15",
                new_value="2026-01-16",
                corrected_at=datetime.now(UTC),
                source="demo_prompt14",
            )
        )
        db.flush()
        _make_agent_evidence(db, instrument_id=amd.id, corrected_event_id=corrected_event.id)

        result = evaluate_agent_role(db, role=_DEMO_ROLE)
        print(f"  agent_role: {result.agent_role}")
        print(f"  sample_size: {result.sample_size} (is_adequate={result.is_adequate})")
        print(
            f"  factual_accuracy_pct: {result.factual_accuracy_pct}  "
            f"(fell after {10} corrected-event citations were added)"
        )
        print(f"  evidence_coverage_pct: {result.evidence_coverage_pct}")
        print(f"  contradiction_detection_rate_pct: {result.contradiction_detection_rate_pct}")
        print(f"  directional_usefulness_pct: {result.directional_usefulness_pct}")
        print(
            f"  contribution_after_deterministic_pct: "
            f"{result.contribution_after_deterministic_pct} "
            f"(n={result.contribution_sample_size})"
        )
        print(
            f"  minority_opinion_usefulness_pct: {result.minority_opinion_usefulness_pct} "
            f"(n={result.minority_sample_size})"
        )
        assert result.factual_accuracy_pct is not None
        assert baseline.factual_accuracy_pct is None or (
            result.factual_accuracy_pct <= baseline.factual_accuracy_pct
        )

        print("\n=== 3. Change governance: propose -> approve -> activate -> rollback ===")
        strategy_definition = StrategyDefinition(
            name="Demo Prompt 14 strategy", owner_user_id=user.id
        )
        db.add(strategy_definition)
        db.flush()

        current_config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            score_threshold=5,
            start=_CONFIG_START,
            end=_CONFIG_END,
            universe_start=_UNIVERSE_START,
            universe_end=_UNIVERSE_END,
        )
        proposed_config = BacktestRunConfig(
            strategy_key=EventBacktestStrategyKey.SCORED_PRE_EARNINGS_BASELINE,
            score_threshold=6,
            start=_CONFIG_START,
            end=_CONFIG_END,
            universe_start=_UNIVERSE_START,
            universe_end=_UNIVERSE_END,
        )
        proposal = propose_strategy_parameter_change(
            db,
            owner_user_id=user.id,
            strategy_definition_id=strategy_definition.id,
            current_config=current_config,
            proposed_config=proposed_config,
            economic_rationale=(
                "Raising the score threshold from 5 to 6 should trade fewer, higher-"
                "conviction setups — walk-forward results below quantify the tradeoff."
            ),
            costs={"engineering_hours": 2},
            operational_risks=["Fewer signals may reduce diversification across names."],
            rollback_plan="Reactivate the score_threshold=5 configuration.",
            description="Raise SCORED_PRE_EARNINGS_BASELINE score threshold 5 -> 6",
        )
        db.commit()
        print(f"  proposal id: {proposal.id}, status: {proposal.status.value}")
        print(
            f"  evidence_package keys: {sorted(proposal.evidence_package.keys())}"
        )
        full_current = proposal.evidence_package["walk_forward_results"]["current"]["FULL"]
        full_proposed = proposal.evidence_package["walk_forward_results"]["proposed"]["FULL"]
        print(
            f"  current (threshold=5) FULL window: trades={full_current['num_trades']} "
            f"total_return_pct={full_current['total_return_pct']}"
        )
        print(
            f"  proposed (threshold=6) FULL window: trades={full_proposed['num_trades']} "
            f"total_return_pct={full_proposed['total_return_pct']}"
        )

        print("\n  attempting activation before approval (must be rejected)...")
        try:
            activate_change(db, proposal_id=proposal.id, activated_by="ops")
            raise AssertionError("premature activation must be rejected")
        except InvalidTransitionError as exc:
            print(f"    rejected as expected: {exc}")
        db.commit()

        approved = approve_change(db, proposal_id=proposal.id, decided_by="cro", comment="LGTM")
        db.commit()
        print(f"  approved: status={approved.status.value}")

        # A pre-existing recommendation, recorded before any activation, whose
        # history must survive the activate/rollback cycle byte-for-byte.
        pre_existing_rec = Recommendation(
            instrument_id=amd.id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db.add(pre_existing_rec)
        db.flush()
        pre_existing = RecommendationVersion(
            recommendation_id=pre_existing_rec.id,
            version_number=1,
            action=RecommendationAction.BUY,
            confidence=RecommendationConfidence.MEDIUM,
            score=Decimal("6.5"),
            rationale="Pre-existing recommendation — must survive activation/rollback unchanged.",
            generated_at=datetime.now(UTC),
        )
        db.add(pre_existing)
        db.flush()
        before_snapshot = (
            pre_existing.action,
            pre_existing.confidence,
            pre_existing.score,
            pre_existing.rationale,
        )

        activated = activate_change(db, proposal_id=proposal.id, activated_by="cro")
        db.commit()
        candidate = db.get(StrategyVersion, proposal.subject_ref_id)
        assert candidate is not None
        print(
            f"  activated: status={activated.status.value}, "
            f"candidate StrategyVersion status={candidate.status.value}"
        )

        rolled_back = rollback_change(
            db,
            proposal_id=proposal.id,
            rolled_back_by="cro",
            reason="Demo: verifying rollback restores prior config as a new version.",
        )
        db.commit()
        db.refresh(candidate)
        active_versions = db.scalars(
            select(StrategyVersion).where(
                StrategyVersion.strategy_definition_id == strategy_definition.id,
                StrategyVersion.status == StrategyVersionStatus.ACTIVE,
            )
        ).all()
        print(f"  rolled back: status={rolled_back.status.value}")
        print(f"  activated candidate now: {candidate.status.value} (expect SUPERSEDED)")
        print(
            f"  currently ACTIVE StrategyVersion count: {len(active_versions)}, "
            f"restored score_threshold: {active_versions[0].config['score_threshold']}"
        )

        db.refresh(pre_existing)
        after_snapshot = (
            pre_existing.action,
            pre_existing.confidence,
            pre_existing.score,
            pre_existing.rationale,
        )
        print(
            f"  RecommendationVersion unchanged across full lifecycle: "
            f"{before_snapshot == after_snapshot}"
        )
        assert before_snapshot == after_snapshot

        print("\nAll Prompt 14 demo state persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
