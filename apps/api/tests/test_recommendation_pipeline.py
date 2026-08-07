"""Pipeline-level tests (Revision Prompt 7) — the pre-flight NO_ACTION
path, "score 5 fails / score 6 may pass only if every other gate
passes," "same symbol receives INVEST_HOLD and TRADE_AVOID without
conflict," and the "baseline six-month configuration" reproducibility
requirement.

**On the six-month baseline test**: this project's historical-replay
backtest engine (`services/backtest.py`, ADR-022..025) was retired at
Phase 8 along with the rest of the shipped MVP's business logic
(ADR-044) and has not been rebuilt — Revision Prompt 7's own scope is
"the deterministic policy layer," not resurrecting the backtest engine.
`TestBaselineSixMonthConfiguration` below substitutes a fixed, hand-
computed synthetic 6-month sequence of earnings events run through the
real deterministic eligibility/sizing functions
(`services/baseline_eligibility.py`, `services/position_sizing.py`) —
proving those functions reproduce a known trade count and aggregate
risk-budget consumption deterministically and reproducibly, which is
the property the prompt's requirement is actually checking for at this
layer. It is not a claim that a full historical market-data backtest
was run."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.services.baseline_eligibility import evaluate_baseline_eligibility
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle, EvidenceItem
from tradingos_api.services.hard_vetoes import HardVetoInputs
from tradingos_api.services.position_sizing import compute_tactical_position_size
from tradingos_api.services.recommendation_pipeline import run_recommendation_pipeline
from tradingos_api.services.side_by_side import get_side_by_side_view


def _seeded_instrument_id(db_session: Session) -> uuid.UUID:
    inst = db_session.scalar(select(Instrument).limit(1))
    assert inst is not None
    return inst.id


def _make_bundle(instrument_id: uuid.UUID) -> CommitteeInputBundle:
    now = datetime.now(UTC)
    return CommitteeInputBundle(
        instrument_id=instrument_id,
        symbol="TEST",
        as_of=now,
        evidence_cutoff=now,
        evidence=[EvidenceItem("ev-1", "NewsItem", "Synthetic evidence.")],
        deterministic_feature_ids=["feat-1"],
        deterministic_summary="synthetic",
        hard_veto_active=False,
        hard_veto_reason=None,
    )


class _NeverCalledLLM:
    """Fails the test immediately if `complete()` is ever invoked — used
    to prove a pre-flight veto stops the pipeline before any committee
    (and any cost) is incurred."""

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise AssertionError("the committee must never run when a pre-flight veto is active")


class TestPreFlightVetoPublishesNoActionWithoutRunningTheCommittee:
    def test_stale_data_veto_short_circuits_before_any_committee_call(
        self, db_session: Session
    ) -> None:
        instrument_id = _seeded_instrument_id(db_session)
        bundle = _make_bundle(instrument_id)
        pre_flight = HardVetoInputs(has_stale_required_data=True, stale_data_detail="test")

        result = run_recommendation_pipeline(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=bundle,
            pre_flight_veto_inputs=pre_flight,
            llm=_NeverCalledLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            per_call_timeout_seconds=30,
            triggered_by="TEST",
        )

        assert result.outcome == "PUBLISHED_NO_ACTION_PRE_FLIGHT"
        assert result.committee_result is None
        assert result.recommendation_version is not None
        assert result.recommendation_version.lane_action == "NO_ACTION"
        assert "STALE_REQUIRED_DATA" in result.recommendation_version.rationale


class TestScoreFiveFailsScoreSixNeedsEveryOtherGate:
    def _passing_kwargs_except_score(self) -> dict[str, Any]:
        return {
            "expected_move_pct": Decimal("5.0"),
            "avg_daily_dollar_volume": Decimal("100_000_000"),
            "num_analyst_estimates": 5,
            "timing_category": "AFTER_CLOSE",
            "evidence_is_fresh": True,
            "has_portfolio_capacity": True,
            "has_sector_capacity": True,
            "has_unresolved_data_quality_issue": False,
        }

    def test_score_5_fails_conservative_live_eligibility(self) -> None:
        result = evaluate_baseline_eligibility(
            direction_score=5, **self._passing_kwargs_except_score()
        )
        assert result.eligible is False
        failing = {c.condition_key for c in result.conditions if not c.passed}
        assert failing == {"DIRECTION_SCORE"}

    def test_score_6_passes_when_every_other_gate_passes(self) -> None:
        result = evaluate_baseline_eligibility(
            direction_score=6, **self._passing_kwargs_except_score()
        )
        assert result.eligible is True

    def test_score_6_still_fails_if_any_other_single_gate_fails(self) -> None:
        kwargs = self._passing_kwargs_except_score()
        kwargs["evidence_is_fresh"] = False
        result = evaluate_baseline_eligibility(direction_score=6, **kwargs)
        assert result.eligible is False
        failing = {c.condition_key for c in result.conditions if not c.passed}
        assert failing == {"FRESH_EVIDENCE"}


class TestSameSymbolInvestHoldAndTradeAvoidCoexist:
    def test_investment_hold_and_tactical_avoid_are_independent_recommendations(
        self, db_session: Session
    ) -> None:
        instrument_id = _seeded_instrument_id(db_session)

        def _cio_args(lane_action: str, lane: str) -> dict[str, Any]:
            common: dict[str, Any] = {
                "recommendation_lane": lane,
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
            }
            if lane == "INVESTMENT":
                common.update(
                    action=lane_action,
                    horizon_days_min=180,
                    horizon_days_max=365,
                    review_date=date.today().isoformat(),
                    valuation_context="N/A",
                    preferred_accumulation_zone="N/A",
                    tranche_plan=None,
                    proposed_max_allocation_pct="5.0",
                    durable_catalysts=[],
                    thesis_break_conditions=["N/A"],
                    portfolio_role="N/A",
                    why_investment_not_trade="N/A",
                    minority_opinion=None,
                )
            else:
                common.update(
                    action=lane_action,
                    setup_and_event_phase="N/A",
                    proposed_holding_window_days_min=1,
                    proposed_holding_window_days_max=5,
                    key_catalyst="N/A",
                    gap_risk="N/A",
                    liquidity_risk="N/A",
                    entry_invalidation="N/A",
                    minority_opinion=None,
                )
            return common

        class _FakeLLM:
            def __init__(self, lane: str, lane_action: str) -> None:
                self._lane = lane
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
                # The base `AgentContractOutput` schema ignores extra
                # fields by default (pydantic v2), so sending the full
                # CIO-shaped payload to every role — analyst or CIO — is
                # harmless and keeps this fake simple.
                args = _cio_args(self._lane_action, self._lane)
                args["agent_role"] = prompt_version
                args["prompt_version"] = prompt_version
                args["evidence_cutoff"] = datetime.now(UTC).isoformat()
                return LLMResponse(
                    prompt_version=prompt_version,
                    model="claude-sonnet-5",
                    stop_reason="tool_use",
                    text=None,
                    tool_calls=[
                        LLMToolCall(
                            tool_use_id="t1", tool_name="submit_agent_output", arguments=args
                        )
                    ],
                    raw_content=[],
                    input_tokens=100,
                    output_tokens=100,
                )

        no_veto = HardVetoInputs(has_stale_required_data=False)

        investment_result = run_recommendation_pipeline(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=_make_bundle(instrument_id),
            pre_flight_veto_inputs=no_veto,
            llm=_FakeLLM("INVESTMENT", "INVEST_HOLD"),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="TEST",
        )
        tactical_result = run_recommendation_pipeline(
            db_session,
            lane=RecommendationMode.TACTICAL,
            bundle=_make_bundle(instrument_id),
            pre_flight_veto_inputs=no_veto,
            llm=_FakeLLM("TACTICAL", "TRADE_AVOID"),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="TEST",
        )

        assert investment_result.recommendation_version is not None
        assert investment_result.recommendation_version.lane_action == "INVEST_HOLD"
        assert tactical_result.recommendation_version is not None
        assert tactical_result.recommendation_version.lane_action == "TRADE_AVOID"
        # Two distinct Recommendation identities for the same instrument —
        # never one row wearing two hats (ADR-046).
        assert investment_result.recommendation is not None
        assert tactical_result.recommendation is not None
        assert investment_result.recommendation.id != tactical_result.recommendation.id

        view = get_side_by_side_view(db_session, instrument_id)
        assert view.investment is not None and view.investment.lane_action == "INVEST_HOLD"
        assert view.tactical is not None and view.tactical.lane_action == "TRADE_AVOID"


class TestBaselineSixMonthConfiguration:
    """Substitutes for a full historical-replay backtest (see module
    docstring) — a fixed, hand-computed 6-month sequence of 6 synthetic
    earnings events (one per month), run through the real deterministic
    eligibility gate, reproduces a known trade count and known aggregate
    risk-budget consumption deterministically and repeatably."""

    _MONTHLY_EVENTS: list[dict[str, Any]] = [
        # (direction_score, expected_move_pct, eligible?)
        {"direction_score": 7, "expected_move_pct": Decimal("6.0"), "expect_eligible": True},
        {"direction_score": 8, "expected_move_pct": Decimal("5.0"), "expect_eligible": True},
        {"direction_score": 5, "expected_move_pct": Decimal("7.0"), "expect_eligible": False},
        {"direction_score": 6, "expected_move_pct": Decimal("3.0"), "expect_eligible": False},
        {"direction_score": 6, "expected_move_pct": Decimal("4.5"), "expect_eligible": True},
        {"direction_score": 8, "expected_move_pct": Decimal("2.0"), "expect_eligible": False},
    ]

    def test_configuration_reproduces_the_expected_trade_count_deterministically(self) -> None:
        def _run() -> tuple[int, Decimal]:
            trade_count = 0
            total_notional = Decimal(0)
            for event in self._MONTHLY_EVENTS:
                eligibility = evaluate_baseline_eligibility(
                    direction_score=event["direction_score"],
                    expected_move_pct=event["expected_move_pct"],
                    avg_daily_dollar_volume=Decimal("100_000_000"),
                    num_analyst_estimates=5,
                    timing_category="AFTER_CLOSE",
                    evidence_is_fresh=True,
                    has_portfolio_capacity=True,
                    has_sector_capacity=True,
                    has_unresolved_data_quality_issue=False,
                )
                assert eligibility.eligible == event["expect_eligible"]
                if eligibility.eligible:
                    trade_count += 1
                    sizing = compute_tactical_position_size(
                        account_equity=Decimal("100000"),
                        risk_budget_pct=Decimal("0.25"),
                        expected_move_pct=event["expected_move_pct"],
                        price=Decimal("50.00"),
                        max_position_pct=Decimal("15.00"),
                        max_sector_pct=Decimal("25.00"),
                        sector_current_notional=Decimal("0"),
                        max_correlated_group_pct=Decimal("25.00"),
                        correlated_group_current_notional=Decimal("0"),
                        avg_daily_dollar_volume=Decimal("100_000_000"),
                        max_liquidity_pct_of_adv=Decimal("1.0"),
                        is_speculative_name=False,
                        speculative_position_pct_cap=Decimal("5.00"),
                        available_cash=Decimal("100000"),
                    )
                    total_notional += sizing.final_notional
            return trade_count, total_notional

        # Run twice — determinism is the property under test, not just a
        # single lucky pass.
        first_count, first_notional = _run()
        second_count, second_notional = _run()

        assert first_count == 3  # events 1, 2, and 5
        assert first_count == second_count
        assert first_notional == second_notional
        assert first_notional > Decimal(0)
