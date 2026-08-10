"""Post-earnings confirmation workflow orchestrator tests (Revision
Prompt 11 task 72) — the state-machine behavior around
`services/post_earnings_confirmation.py`/`services/post_confirmation_gate.py`/
`services/recommendation_pipeline.py`: WAITING_FOR_DATA holding states,
the price-confirmation window, reversal invalidation, HES-6's absolute
negative-gap rule, and idempotent replay (duplicate release / worker
restart)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    PostEarningsWorkflowStatus,
    RecommendationMode,
    RecommendationStatus,
)
from tradingos_api.models.execution import Account
from tradingos_api.models.market_evidence import EarningsConsensusSnapshot, EarningsGuidanceItem
from tradingos_api.models.market_evidence import EarningsEvent as EarningsEventModel
from tradingos_api.models.monitoring import PostEarningsWorkflowRun
from tradingos_api.models.operations import Alert
from tradingos_api.models.recommendations import Recommendation
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.providers.synthetic_evidence import SyntheticEarningsActualsProvider
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle, EvidenceItem
from tradingos_api.services.hard_vetoes import HardVetoInputs
from tradingos_api.services.post_earnings_workflow import (
    PostEarningsMarketContext,
    TacticalPipelineInputs,
    run_post_earnings_workflow,
)


def _amd_instrument_id(db_session: Session) -> uuid.UUID:
    amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert amd is not None
    return amd.id


def _fresh_event(db_session: Session) -> EarningsEventModel:
    event = EarningsEventModel(
        instrument_id=_amd_instrument_id(db_session),
        fiscal_period="Q3-2026",
        report_date=date(2026, 9, 1),
        source="test_fixture",
    )
    db_session.add(event)
    db_session.flush()
    return event


def _frozen_consensus(db_session: Session, event_id: uuid.UUID) -> EarningsConsensusSnapshot:
    snapshot = EarningsConsensusSnapshot(
        earnings_event_id=event_id,
        as_of=date(2026, 8, 25),
        consensus_eps=Decimal("1.1500"),
        consensus_revenue=Decimal("8200000000.00"),
        num_analysts=32,
        source="test_fixture",
        observed_at=datetime(2026, 8, 25, tzinfo=UTC),
        usable_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def _passing_market_context() -> PostEarningsMarketContext:
    return PostEarningsMarketContext(
        gap_pct=Decimal("3.0"),
        session_open=Decimal("100"),
        session_close=Decimal("105"),
        has_intraday_capability=False,
        range_30min_pct=None,
        range_60min_pct=None,
        price_vs_vwap_pct=None,
        day_volume=None,
        baseline_avg_volume=None,
        instrument_return_pct=Decimal("3.0"),
        sector_return_pct=Decimal("1.0"),
        market_return_pct=Decimal("0.5"),
        liquidity_passed=True,
    )


def _tactical_cio_args(lane_action: str) -> dict[str, Any]:
    """Matches `test_recommendation_pipeline.py`'s own `_cio_args()` TACTICAL
    branch exactly — the base `AgentContractOutput` schema ignores extra
    fields, but every field the real `TradingCioOutput` schema requires
    must be present or the agent run fails validation and the committee
    never produces a recommendation (silently leaving `recommendation=None`,
    not a raised error — the bug this helper avoids re-introducing)."""
    return {
        "recommendation_lane": "TACTICAL",
        "evidence_ids": ["ev-1"],
        "factual_claims": [],
        "deterministic_feature_ids": ["feat-1"],
        "thesis": f"Synthetic {lane_action} case.",
        "strongest_supporting_evidence": "N/A",
        "strongest_contradictory_evidence": "N/A",
        "risks": [],
        "missing_information": [],
        "invalidation_conditions": ["N/A"],
        "categorical_stance": "NEUTRAL",
        "evidence_completeness": "MEDIUM",
        "action": lane_action,
        "setup_and_event_phase": "N/A",
        "proposed_holding_window_days_min": 1,
        "proposed_holding_window_days_max": 5,
        "key_catalyst": "N/A",
        "gap_risk": "N/A",
        "liquidity_risk": "N/A",
        "entry_invalidation": "N/A",
        "minority_opinion": None,
    }


class _FakeLLM:
    def __init__(self, lane_action: str) -> None:
        self._lane_action = lane_action

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> LLMResponse:
        args = _tactical_cio_args(self._lane_action)
        args["agent_role"] = prompt_version
        args["prompt_version"] = prompt_version
        args["evidence_cutoff"] = datetime.now(UTC).isoformat()
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(tool_use_id="t1", tool_name="submit_agent_output", arguments=args)
            ],
            raw_content=[],
            input_tokens=100,
            output_tokens=100,
        )


def _tactical_inputs(
    instrument_id: uuid.UUID, event_id: uuid.UUID, lane_action: str
) -> TacticalPipelineInputs:
    now = datetime.now(UTC)
    bundle = CommitteeInputBundle(
        instrument_id=instrument_id,
        symbol="AMD",
        as_of=now,
        evidence_cutoff=now,
        evidence=[EvidenceItem("ev-1", "EarningsActual", "Synthetic post-earnings evidence.")],
        deterministic_feature_ids=["feat-1"],
        deterministic_summary="synthetic post-confirmation bundle",
        hard_veto_active=False,
        hard_veto_reason=None,
        earnings_event_id=event_id,
    )
    return TacticalPipelineInputs(
        bundle=bundle,
        pre_flight_veto_inputs=HardVetoInputs(has_stale_required_data=False),
        llm=_FakeLLM(lane_action),
        cost_ceiling_usd=Decimal("5.00"),
        per_call_timeout_seconds=30,
        triggered_by="TEST",
    )


class TestWaitingForData:
    def test_no_release_yet_stays_waiting(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q4-2026",  # not fixtured -> no actuals yet
            actuals_provider=SyntheticEarningsActualsProvider(),
        )
        assert result.run.status == PostEarningsWorkflowStatus.WAITING_FOR_DATA
        assert result.run.results_ingested_at is None

    def test_confirmation_window_not_yet_elapsed_stays_waiting(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        now = datetime.now(UTC)
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=now,
            confirmation_window=timedelta(minutes=30),
            market_context=_passing_market_context(),
        )
        assert result.run.status == PostEarningsWorkflowStatus.WAITING_FOR_DATA
        assert result.run.results_ingested_at is not None
        assert result.run.confirmation_window_ends_at is not None

    def test_missing_frozen_consensus_stays_waiting(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(),
        )
        assert result.run.status == PostEarningsWorkflowStatus.WAITING_FOR_DATA
        assert "consensus" in (result.run.detail or "")

    def test_missing_market_context_stays_waiting(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=None,
        )
        assert result.run.status == PostEarningsWorkflowStatus.WAITING_FOR_DATA
        assert "price" in (result.run.detail or "").lower()


class TestReversalInvalidation:
    def test_reversed_intraday_move_invalidates_the_add(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        # Gap up, but session closes BELOW the open — a reversal.
        market_context = PostEarningsMarketContext(
            gap_pct=Decimal("3.0"),
            session_open=Decimal("100"),
            session_close=Decimal("95"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=None,
            baseline_avg_volume=None,
            instrument_return_pct=Decimal("-5.0"),
            sector_return_pct=Decimal("1.0"),
            market_return_pct=Decimal("0.5"),
            liquidity_passed=True,
        )
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=market_context,
        )
        assert result.run.status == PostEarningsWorkflowStatus.INVALIDATED
        assert result.run.reversal_detected is True


class TestHardVeto6NegativeGap:
    def test_negative_gap_fails_regardless_of_other_gates(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        market_context = PostEarningsMarketContext(
            gap_pct=Decimal("-2.0"),
            session_open=Decimal("100"),
            session_close=Decimal("98"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=None,
            baseline_avg_volume=None,
            instrument_return_pct=Decimal("-2.0"),
            sector_return_pct=Decimal("-1.0"),
            market_return_pct=Decimal("-0.5"),
            liquidity_passed=True,
        )
        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=market_context,
        )
        assert result.run.status == PostEarningsWorkflowStatus.FAILED
        assert "HES-6" in (result.run.detail or "")


class TestConfirmedHappyPath:
    def test_eligible_confirmation_runs_the_tactical_desk_and_confirms(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        db_session.add(
            EarningsGuidanceItem(
                earnings_event_id=event.id,
                metric="revenue",
                guidance_low=Decimal("8300000000.00"),
                guidance_high=Decimal("8500000000.00"),
                guidance_midpoint=Decimal("8400000000.00"),
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="test_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db_session.flush()

        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(),
            tactical_pipeline_inputs=_tactical_inputs(
                event.instrument_id, event.id, "TRADE_ADD_CONFIRMED"
            ),
        )
        assert result.run.status == PostEarningsWorkflowStatus.CONFIRMED
        assert result.run.post_event_recommendation_id is not None
        assert result.pipeline_result is not None
        assert result.pipeline_result.recommendation_version is not None
        assert result.pipeline_result.recommendation_version.lane_action == "TRADE_ADD_CONFIRMED"

    def test_post_event_recommendation_is_never_the_pre_event_one(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        db_session.add(
            EarningsGuidanceItem(
                earnings_event_id=event.id,
                metric="revenue",
                guidance_midpoint=Decimal("8400000000.00"),
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="test_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db_session.flush()
        pre_event_recommendation = Recommendation(
            instrument_id=event.instrument_id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db_session.add(pre_event_recommendation)
        db_session.flush()
        pre_event_id = pre_event_recommendation.id

        result = run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            pre_event_recommendation_id=pre_event_id,
            market_context=_passing_market_context(),
            tactical_pipeline_inputs=_tactical_inputs(event.instrument_id, event.id, "TRADE_HOLD"),
        )
        assert result.run.pre_event_recommendation_id == pre_event_id
        assert result.run.post_event_recommendation_id != pre_event_id


class TestIdempotentReplay:
    def test_duplicate_release_does_not_create_a_second_run_row(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        account_id = fresh_account.id
        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=account_id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
        )
        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=account_id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
        )
        rows = db_session.scalars(
            select(PostEarningsWorkflowRun).where(
                PostEarningsWorkflowRun.earnings_event_id == event.id,
                PostEarningsWorkflowRun.account_id == account_id,
            )
        ).all()
        assert len(rows) == 1

    def test_worker_restart_on_a_terminal_run_is_a_safe_no_op(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        market_context = PostEarningsMarketContext(
            gap_pct=Decimal("-2.0"),
            session_open=Decimal("100"),
            session_close=Decimal("98"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=None,
            baseline_avg_volume=None,
            instrument_return_pct=Decimal("-2.0"),
            sector_return_pct=Decimal("-1.0"),
            market_return_pct=Decimal("-0.5"),
            liquidity_passed=True,
        )
        account_id = fresh_account.id
        kwargs: dict[str, Any] = {
            "owner_user_id": seeded_user_id,
            "earnings_event_id": event.id,
            "instrument_id": event.instrument_id,
            "account_id": account_id,
            "ticker": "AMD",
            "fiscal_period": "Q3-2026",
            "actuals_provider": SyntheticEarningsActualsProvider(),
            "now": datetime.now(UTC) + timedelta(hours=1),
            "market_context": market_context,
        }
        first = run_post_earnings_workflow(db_session, **kwargs)
        assert first.run.status == PostEarningsWorkflowStatus.FAILED

        # Simulate a restarted worker re-invoking the same workflow —
        # must not re-evaluate or change the terminal outcome.
        second = run_post_earnings_workflow(db_session, **kwargs)
        assert second.run.id == first.run.id
        assert second.run.status == PostEarningsWorkflowStatus.FAILED
        assert second.run.detail == first.run.detail


class TestAlertsAreActuallyEmitted:
    """The workflow's own alert emission (Prompt 11's alert taxonomy for
    RESULTS_AVAILABLE, POST_EARNINGS_CONFIRMATION_READY/FAILED, and
    THESIS_INVALIDATED) — not just the status-field bookkeeping the other
    test classes check."""

    def _alerts_for(self, db_session: Session, instrument_id: uuid.UUID) -> list[Alert]:
        return list(
            db_session.scalars(select(Alert).where(Alert.instrument_id == instrument_id)).all()
        )

    def test_eligible_confirmation_emits_results_available_and_confirmation_ready(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        db_session.add(
            EarningsGuidanceItem(
                earnings_event_id=event.id,
                metric="revenue",
                guidance_midpoint=Decimal("8400000000.00"),
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="test_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db_session.flush()

        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(),
            tactical_pipeline_inputs=_tactical_inputs(event.instrument_id, event.id, "TRADE_HOLD"),
        )
        alert_types = {
            a.alert_type.value for a in self._alerts_for(db_session, event.instrument_id)
        }
        assert "RESULTS_AVAILABLE" in alert_types
        assert "POST_EARNINGS_CONFIRMATION_READY" in alert_types

    def test_reversal_emits_thesis_invalidated(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        market_context = PostEarningsMarketContext(
            gap_pct=Decimal("3.0"),
            session_open=Decimal("100"),
            session_close=Decimal("95"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=None,
            baseline_avg_volume=None,
            instrument_return_pct=Decimal("-5.0"),
            sector_return_pct=Decimal("1.0"),
            market_return_pct=Decimal("0.5"),
            liquidity_passed=True,
        )
        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=market_context,
        )
        alert_types = {
            a.alert_type.value for a in self._alerts_for(db_session, event.instrument_id)
        }
        assert "THESIS_INVALIDATED" in alert_types

    def test_negative_gap_failure_emits_confirmation_failed(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)
        market_context = PostEarningsMarketContext(
            gap_pct=Decimal("-2.0"),
            session_open=Decimal("100"),
            session_close=Decimal("98"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=None,
            baseline_avg_volume=None,
            instrument_return_pct=Decimal("-2.0"),
            sector_return_pct=Decimal("-1.0"),
            market_return_pct=Decimal("-0.5"),
            liquidity_passed=True,
        )
        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=market_context,
        )
        alert_types = {
            a.alert_type.value for a in self._alerts_for(db_session, event.instrument_id)
        }
        assert "POST_EARNINGS_CONFIRMATION_FAILED" in alert_types

    def test_beat_with_lowered_guidance_emits_guidance_conflict(
        self, db_session: Session, fresh_account: Account, seeded_user_id: uuid.UUID
    ) -> None:
        """Required test category "conflicting guidance" (Revision Prompt
        11) — a genuine EPS/revenue beat alongside formally lowered
        guidance is exactly the conflicting-signal case
        `AlertType.GUIDANCE_CONFLICT` exists to surface, independent of
        whatever the eligibility gate ultimately decides."""
        event = _fresh_event(db_session)
        _frozen_consensus(db_session, event.id)  # consensus_revenue = 8.2B
        db_session.add(
            EarningsGuidanceItem(
                earnings_event_id=event.id,
                metric="revenue",
                guidance_low=Decimal("7800000000.00"),
                guidance_high=Decimal("8000000000.00"),
                guidance_midpoint=Decimal("7900000000.00"),  # below the 8.2B consensus
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="test_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db_session.flush()

        run_post_earnings_workflow(
            db_session,
            owner_user_id=seeded_user_id,
            earnings_event_id=event.id,
            instrument_id=event.instrument_id,
            account_id=fresh_account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",  # actual EPS 1.22 beats the 1.15 consensus
            actuals_provider=SyntheticEarningsActualsProvider(),
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(),
        )
        alert_types = {
            a.alert_type.value for a in self._alerts_for(db_session, event.instrument_id)
        }
        assert "GUIDANCE_CONFLICT" in alert_types
