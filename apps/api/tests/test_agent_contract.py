"""Agent Contract schema validation tests (Revision Prompt 6) — the
"reject unsupported factual claims" requirement, and the CIO schemas'
own extra constraints (action validated against the lane's vocabulary,
horizon/window ordering)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from tradingos_api.schemas.agent_contract import (
    AgentContractOutput,
    FactualClaim,
    InvestmentCioOutput,
    RunMetadata,
    TradingCioOutput,
)


def _base_kwargs() -> dict:
    return {
        "agent_role": "LONG_TERM_BULL_ANALYST",
        "prompt_version": "investment-long-term-bull-v1",
        "recommendation_lane": "INVESTMENT",
        "evidence_cutoff": datetime.now(UTC),
        "evidence_ids": ["ev-1", "ev-2"],
        "factual_claims": [FactualClaim(claim="Revenue grew 20%", evidence_ids=["ev-1"])],
        "deterministic_feature_ids": ["feat-1"],
        "thesis": "Strong durable business.",
        "strongest_supporting_evidence": "Revenue growth.",
        "strongest_contradictory_evidence": "Valuation is rich.",
        "risks": ["Execution risk"],
        "missing_information": [],
        "invalidation_conditions": ["Revenue growth turns negative"],
        "categorical_stance": "BULLISH",
        "evidence_completeness": "HIGH",
        "run_metadata": RunMetadata(
            model="claude-sonnet-5",
            input_tokens=500,
            output_tokens=300,
            latency_ms=1200,
            cost_usd="0.006",
        ),
    }


class TestRejectsUnsupportedFactualClaims:
    def test_claim_citing_an_undeclared_evidence_id_is_rejected(self) -> None:
        kwargs = _base_kwargs()
        kwargs["factual_claims"] = [FactualClaim(claim="Revenue grew 20%", evidence_ids=["ev-999"])]
        with pytest.raises(ValidationError, match="undeclared evidence"):
            AgentContractOutput(**kwargs)

    def test_claim_citing_a_declared_evidence_id_is_accepted(self) -> None:
        output = AgentContractOutput(**_base_kwargs())
        assert output.factual_claims[0].evidence_ids == ["ev-1"]

    def test_factual_claim_requires_at_least_one_evidence_id(self) -> None:
        with pytest.raises(ValidationError):
            FactualClaim(claim="Unsupported assertion", evidence_ids=[])


class TestInvestmentCioOutput:
    def _cio_kwargs(self) -> dict:
        kwargs = _base_kwargs()
        kwargs.update(
            action="INVEST_BUY",
            horizon_days_min=180,
            horizon_days_max=365,
            review_date=date.today(),
            valuation_context="Trading below sector median P/E.",
            durable_catalysts=["New product cycle"],
            thesis_break_conditions=["Loses market share for 2 quarters"],
            portfolio_role="Core holding.",
            minority_opinion=None,
        )
        return kwargs

    def test_valid_investment_action_is_accepted(self) -> None:
        output = InvestmentCioOutput(**self._cio_kwargs())
        assert output.action.value == "INVEST_BUY"

    def test_tactical_action_is_rejected_under_investment_schema(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["action"] = "TRADE_ENTER"
        with pytest.raises(ValidationError):
            InvestmentCioOutput(**kwargs)

    def test_horizon_min_greater_than_max_is_rejected(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["horizon_days_min"] = 400
        kwargs["horizon_days_max"] = 200
        with pytest.raises(ValidationError, match="horizon_days_min"):
            InvestmentCioOutput(**kwargs)

    def test_horizon_below_three_months_is_rejected(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["horizon_days_min"] = 10
        with pytest.raises(ValidationError):
            InvestmentCioOutput(**kwargs)


class TestTradingCioOutput:
    def _cio_kwargs(self) -> dict:
        kwargs = _base_kwargs()
        kwargs.update(
            recommendation_lane="TACTICAL",
            action="TRADE_ENTER",
            setup_and_event_phase="Pre-earnings, after-close report expected.",
            proposed_holding_window_days_min=1,
            proposed_holding_window_days_max=5,
            key_catalyst="Quarterly earnings report",
            gap_risk="Moderate — median prior gap is 6%",
            liquidity_risk="Low — ADV exceeds $100M",
            entry_invalidation="Price closes below the pre-earnings low",
            minority_opinion=None,
        )
        return kwargs

    def test_valid_tactical_action_is_accepted(self) -> None:
        output = TradingCioOutput(**self._cio_kwargs())
        assert output.action.value == "TRADE_ENTER"

    def test_investment_action_is_rejected_under_tactical_schema(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["action"] = "INVEST_BUY"
        with pytest.raises(ValidationError):
            TradingCioOutput(**kwargs)

    def test_holding_window_min_greater_than_max_is_rejected(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["proposed_holding_window_days_min"] = 8
        kwargs["proposed_holding_window_days_max"] = 3
        with pytest.raises(ValidationError, match="proposed_holding_window"):
            TradingCioOutput(**kwargs)

    def test_holding_window_over_ten_days_is_rejected(self) -> None:
        kwargs = self._cio_kwargs()
        kwargs["proposed_holding_window_days_max"] = 15
        with pytest.raises(ValidationError):
            TradingCioOutput(**kwargs)
