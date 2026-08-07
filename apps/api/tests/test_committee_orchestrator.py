"""Committee orchestrator eval fixtures (Revision Prompt 6): a handful
of hand-constructed evidence bundles with known "obviously bullish,"
"obviously bearish/blocked," and "adversarial CIO tries to override the
veto" cases — asserting each role's structured output is well-formed and
that the CIO's final action respects the deterministic veto, matching
docs/MODEL_GOVERNANCE.md's own "Evaluation" section's stated scope (not
grading narrative quality — that's out of scope for automated tests).

All against a fake `LLMProvider` and the real `db_session` fixture
(rolled back after each test) — no network call, no real Anthropic
spend."""

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
from tradingos_api.services.committee_orchestrator import (
    CommitteeInputBundle,
    EvidenceItem,
    run_committee,
)

_INVESTMENT_ANALYST_ARGS: dict[str, Any] = {
    "recommendation_lane": "INVESTMENT",
    "evidence_ids": ["ev-1"],
    "factual_claims": [{"claim": "Revenue grew 20%", "evidence_ids": ["ev-1"]}],
    "deterministic_feature_ids": ["feat-1"],
    "thesis": "Business quality is strong and improving.",
    "strongest_supporting_evidence": "Revenue growth of 20% year over year.",
    "strongest_contradictory_evidence": "Margins flat this quarter.",
    "risks": ["Competitive pressure"],
    "missing_information": [],
    "invalidation_conditions": ["Revenue growth turns negative"],
    "categorical_stance": "BULLISH",
    "evidence_completeness": "HIGH",
}

_INVESTMENT_CIO_BUY_ARGS: dict[str, Any] = {
    "recommendation_lane": "INVESTMENT",
    "evidence_ids": ["ev-1"],
    "factual_claims": [],
    "deterministic_feature_ids": ["feat-1"],
    "thesis": "Strong durable business at a fair price.",
    "strongest_supporting_evidence": "Revenue growth accelerating.",
    "strongest_contradictory_evidence": "Valuation slightly rich.",
    "risks": ["Execution risk"],
    "missing_information": [],
    "invalidation_conditions": ["Margin compression for 2 consecutive quarters"],
    "categorical_stance": "BULLISH",
    "evidence_completeness": "HIGH",
    "action": "INVEST_BUY",
    "horizon_days_min": 180,
    "horizon_days_max": 365,
    "review_date": None,  # filled in per-test
    "valuation_context": "Trading below sector median P/E.",
    "preferred_accumulation_zone": "On pullbacks toward the 50-day moving average.",
    "tranche_plan": "Three equal tranches over 60 days.",
    "proposed_max_allocation_pct": "5.0",
    "durable_catalysts": ["New product cycle"],
    "thesis_break_conditions": ["Loses market share for 2 quarters"],
    "portfolio_role": "Core long-term holding.",
    "why_investment_not_trade": "Multi-year durability thesis, not a short-term catalyst trade.",
    "minority_opinion": None,
}


def _make_fake_llm(analyst_args: dict[str, Any], cio_args: dict[str, Any]) -> Any:
    class _FakeLLM:
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
            is_cio = "cio" in prompt_version
            args = dict(cio_args if is_cio else analyst_args)
            args["agent_role"] = prompt_version
            args["prompt_version"] = prompt_version
            args.setdefault("evidence_cutoff", datetime.now(UTC).isoformat())
            return LLMResponse(
                prompt_version=prompt_version,
                model="claude-sonnet-5",
                stop_reason="tool_use",
                text=None,
                tool_calls=[
                    LLMToolCall(tool_use_id="t1", tool_name="submit_agent_output", arguments=args)
                ],
                raw_content=[],
                input_tokens=500,
                output_tokens=300,
            )

    return _FakeLLM()


def _seeded_instrument_id(db_session: Session) -> uuid.UUID:
    inst = db_session.scalar(select(Instrument).limit(1))
    assert inst is not None
    return inst.id


class TestObviouslyBullishEligibleInvestmentRun:
    def test_all_eight_roles_succeed_and_cio_writes_invest_buy(self, db_session: Session) -> None:
        instrument_id = _seeded_instrument_id(db_session)
        cio_args = dict(_INVESTMENT_CIO_BUY_ARGS)
        cio_args["review_date"] = date.today().isoformat()
        llm = _make_fake_llm(_INVESTMENT_ANALYST_ARGS, cio_args)

        bundle = CommitteeInputBundle(
            instrument_id=instrument_id,
            symbol="TEST",
            as_of=datetime.now(UTC),
            evidence_cutoff=datetime.now(UTC),
            evidence=[EvidenceItem("ev-1", "NewsItem", "20% revenue growth reported.")],
            deterministic_feature_ids=["feat-1"],
            deterministic_summary="REVENUE_EARNINGS_GROWTH: PASS (40.0); hard_disqualified: False",
            hard_veto_active=False,
            hard_veto_reason=None,
        )
        result = run_committee(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=bundle,
            llm=llm,
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="EVAL_FIXTURE",
        )

        assert len(result.role_runs) == 8
        assert all(rr.outcome.status == "SUCCEEDED" for rr in result.role_runs)
        assert result.recommendation is not None
        assert result.recommendation_version is not None
        assert result.recommendation_version.lane_action == "INVEST_BUY"
        assert result.veto_override_applied is False


class TestDeterministicVetoCannotBeOverridden:
    def test_cio_insisting_on_invest_buy_is_forced_to_invest_watch(
        self, db_session: Session
    ) -> None:
        """The adversarial case: the CIO's own structured output argues
        for `INVEST_BUY` despite an active hard-disqualification veto.
        The orchestrator must still write `INVEST_WATCH` — proving the
        veto is enforced in code, not merely requested in the prompt."""
        instrument_id = _seeded_instrument_id(db_session)
        cio_args = dict(_INVESTMENT_CIO_BUY_ARGS)
        cio_args["review_date"] = date.today().isoformat()
        cio_args["thesis"] = "CIO insists on buying despite the going-concern flag."
        llm = _make_fake_llm(_INVESTMENT_ANALYST_ARGS, cio_args)

        bundle = CommitteeInputBundle(
            instrument_id=instrument_id,
            symbol="TEST",
            as_of=datetime.now(UTC),
            evidence_cutoff=datetime.now(UTC),
            evidence=[EvidenceItem("ev-1", "NewsItem", "Auditor raises going-concern flag.")],
            deterministic_feature_ids=["feat-1"],
            deterministic_summary="hard_disqualified: True",
            hard_veto_active=True,
            hard_veto_reason="going-concern flag is set",
        )
        result = run_committee(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=bundle,
            llm=llm,
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="EVAL_FIXTURE",
        )

        assert result.recommendation_version is not None
        assert result.recommendation_version.lane_action == "INVEST_WATCH"
        assert result.veto_override_applied is True
        assert "DETERMINISTIC VETO OVERRIDE" in result.recommendation_version.rationale

    def test_veto_active_but_cio_already_says_watch_needs_no_override(
        self, db_session: Session
    ) -> None:
        instrument_id = _seeded_instrument_id(db_session)
        cio_args = dict(_INVESTMENT_CIO_BUY_ARGS)
        cio_args["review_date"] = date.today().isoformat()
        cio_args["action"] = "INVEST_WATCH"
        llm = _make_fake_llm(_INVESTMENT_ANALYST_ARGS, cio_args)

        bundle = CommitteeInputBundle(
            instrument_id=instrument_id,
            symbol="TEST",
            as_of=datetime.now(UTC),
            evidence_cutoff=datetime.now(UTC),
            evidence=[EvidenceItem("ev-1", "NewsItem", "Auditor raises going-concern flag.")],
            deterministic_feature_ids=["feat-1"],
            deterministic_summary="hard_disqualified: True",
            hard_veto_active=True,
            hard_veto_reason="going-concern flag is set",
        )
        result = run_committee(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=bundle,
            llm=llm,
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="EVAL_FIXTURE",
        )
        assert result.recommendation_version is not None
        assert result.recommendation_version.lane_action == "INVEST_WATCH"
        assert result.veto_override_applied is False  # already compliant, nothing to override


class TestDegradedAnalystDoesNotBlockTheRestOfTheCommittee:
    def test_one_role_failing_schema_validation_does_not_stop_other_roles(
        self, db_session: Session
    ) -> None:
        instrument_id = _seeded_instrument_id(db_session)

        class _FlakyFirstRoleLLM:
            def __init__(self) -> None:
                self.calls = 0

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
                self.calls += 1
                is_cio = "cio" in prompt_version
                if self.calls == 1:
                    # First analyst returns malformed (missing required fields).
                    args: dict[str, Any] = {"agent_role": prompt_version}
                elif is_cio:
                    args = dict(_INVESTMENT_CIO_BUY_ARGS)
                    args["review_date"] = date.today().isoformat()
                    args["agent_role"] = prompt_version
                    args["prompt_version"] = prompt_version
                    args["evidence_cutoff"] = datetime.now(UTC).isoformat()
                else:
                    args = dict(_INVESTMENT_ANALYST_ARGS)
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
                    output_tokens=50,
                )

        bundle = CommitteeInputBundle(
            instrument_id=instrument_id,
            symbol="TEST",
            as_of=datetime.now(UTC),
            evidence_cutoff=datetime.now(UTC),
            evidence=[EvidenceItem("ev-1", "NewsItem", "20% revenue growth reported.")],
            deterministic_feature_ids=["feat-1"],
            deterministic_summary="REVENUE_EARNINGS_GROWTH: PASS (40.0)",
            hard_veto_active=False,
            hard_veto_reason=None,
        )
        result = run_committee(
            db_session,
            lane=RecommendationMode.INVESTMENT,
            bundle=bundle,
            llm=_FlakyFirstRoleLLM(),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="EVAL_FIXTURE",
        )

        assert len(result.role_runs) == 8
        assert result.role_runs[0].outcome.status == "FAILED"
        assert all(rr.outcome.status == "SUCCEEDED" for rr in result.role_runs[1:])
        assert result.recommendation is not None  # CIO still ran and produced a result
