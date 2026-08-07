"""The Agent Contract (Revision Prompt 6) — every committee-role output,
Investment or Tactical, analyst or CIO, is validated against this one
shared shape before it is ever persisted or shown. Both committees call
through the single provider-neutral `LLMProvider` adapter
(`providers/llm.py`) that already existed from ADR-020 — no second
adapter is introduced for this revision.

`AgentContractOutput` carries every field the prompt's own "Every output
must include" list requires. `InvestmentCioOutput`/`TradingCioOutput`
extend it with the two CIO roles' lane-specific required fields —
deliberately two separate schemas, not one schema with optional fields
for both lanes, because "they must not share a conclusion or silently
reuse a horizon" (Revision Prompt 6) is easiest to guarantee when the
two shapes cannot structurally be confused for one another (the same
"never one row wearing two hats" philosophy ADR-046 already established
for `Recommendation.mode`).

Nothing here calculates a score, an expected move, a position size, or
portfolio risk — those are Revision Prompt 5's deterministic services;
this module only validates what an LLM is allowed to *say* about them."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from tradingos_api.policy.recommendation_modes import (
    InvestmentAction,
    RecommendationMode,
    TacticalAction,
    assert_action_valid_for_mode,
)

EvidenceCompleteness = Literal["LOW", "MEDIUM", "HIGH"]

# Never "calibrated" or a bare probability — restates DQ-5/principle 15 as
# a literal schema constraint: an LLM cannot self-report a probability
# through this contract even if it wanted to. "PRELIMINARY" is reserved
# for a future phase once real outcome data exists (docs/MODEL_GOVERNANCE.md).
CalibrationStatus = Literal["UNCALIBRATED"]

CategoricalStance = Literal["BULLISH", "BEARISH", "NEUTRAL"]


class RunMetadata(BaseModel):
    """ "Model, token, latency, and cost metadata" — sourced from
    `providers.llm.LLMResponse` plus a wall-clock measurement around the
    call, never self-reported by the model itself."""

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)


class FactualClaim(BaseModel):
    """A single assertion the agent is making, mapped to the specific
    evidence id(s) it rests on. `evidence_ids` must be non-empty — a
    "factual claim" with no cited evidence is, by construction, not a
    factual claim (it belongs in `thesis` narrative instead)."""

    claim: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class AgentContractOutput(BaseModel):
    agent_role: str
    prompt_version: str
    recommendation_lane: RecommendationMode
    evidence_cutoff: datetime
    evidence_ids: list[str]
    factual_claims: list[FactualClaim] = Field(default_factory=list)
    deterministic_feature_ids: list[str] = Field(default_factory=list)
    thesis: str = Field(min_length=1)
    strongest_supporting_evidence: str = Field(min_length=1)
    strongest_contradictory_evidence: str = Field(min_length=1)
    risks: list[str]
    missing_information: list[str]
    invalidation_conditions: list[str]
    categorical_stance: CategoricalStance
    evidence_completeness: EvidenceCompleteness
    calibration_status: CalibrationStatus = "UNCALIBRATED"
    run_metadata: RunMetadata

    @model_validator(mode="after")
    def _reject_unsupported_factual_claims(self) -> AgentContractOutput:
        """ "Reject unsupported factual claims" (Revision Prompt 6's own
        wording) — every `evidence_ids` entry a claim cites must be one
        of this output's own declared `evidence_ids`; a claim citing an
        id the agent never listed as evidence it consulted is rejected
        outright, not silently accepted or trimmed."""
        declared = set(self.evidence_ids)
        for claim in self.factual_claims:
            unknown = [e for e in claim.evidence_ids if e not in declared]
            if unknown:
                raise ValueError(
                    f"factual claim {claim.claim!r} cites undeclared evidence "
                    f"id(s) {unknown} — every cited id must appear in evidence_ids"
                )
        return self


class InvestmentCioOutput(AgentContractOutput):
    """Investment CIO output (Revision Prompt 6, extended Revision
    Prompt 7 with the remaining "INVESTMENT ACTION PLAN" fields).
    `action` is validated against `policy.recommendation_modes.InvestmentAction`
    — the same enum `RecommendationVersion.lane_action` is already
    validated against (R0/R3), so a CIO output that passes this schema
    is, by construction, writable as a real `RecommendationVersion` row.

    `proposed_max_allocation_pct` is this specific thesis's own proposed
    ceiling, not a calculated position size — the CIO may propose a
    number, but `services/recommendation_pipeline.py` clamps it against
    `RiskPolicy.max_position_pct` deterministically before anything is
    persisted (principle 6/7: the model proposes, the policy layer
    decides). No numeric valuation range (low/mid/high) is requested
    here deliberately — a number like that would be exactly the kind of
    calculation an LLM must not produce; `valuation_context` is
    qualitative narrative only, and a real numeric valuation range
    requires a deterministic valuation model this revision does not
    build (documented limitation, not an oversight)."""

    action: InvestmentAction
    horizon_days_min: int = Field(ge=90)  # ~3 months
    horizon_days_max: int = Field(le=730)  # ~24 months
    review_date: date
    valuation_context: str = Field(min_length=1)
    preferred_accumulation_zone: str = Field(min_length=1)
    tranche_plan: str | None = None
    proposed_max_allocation_pct: Decimal = Field(gt=0, le=100)
    durable_catalysts: list[str]
    thesis_break_conditions: list[str] = Field(min_length=1)
    portfolio_role: str = Field(min_length=1)
    why_investment_not_trade: str = Field(min_length=1)
    minority_opinion: str | None = None

    @model_validator(mode="after")
    def _validate_action_and_horizon(self) -> InvestmentCioOutput:
        assert_action_valid_for_mode(RecommendationMode.INVESTMENT, self.action.value)
        if self.horizon_days_min > self.horizon_days_max:
            raise ValueError("horizon_days_min must be <= horizon_days_max")
        return self


class TradingCioOutput(AgentContractOutput):
    """Trading CIO output (Revision Prompt 6). `action` is validated
    against `policy.recommendation_modes.TacticalAction`."""

    action: TacticalAction
    setup_and_event_phase: str = Field(min_length=1)
    proposed_holding_window_days_min: int = Field(ge=1)
    proposed_holding_window_days_max: int = Field(le=10)
    key_catalyst: str = Field(min_length=1)
    gap_risk: str = Field(min_length=1)
    liquidity_risk: str = Field(min_length=1)
    entry_invalidation: str = Field(min_length=1)
    minority_opinion: str | None = None

    @model_validator(mode="after")
    def _validate_action_and_window(self) -> TradingCioOutput:
        assert_action_valid_for_mode(RecommendationMode.TACTICAL, self.action.value)
        if self.proposed_holding_window_days_min > self.proposed_holding_window_days_max:
            raise ValueError(
                "proposed_holding_window_days_min must be <= proposed_holding_window_days_max"
            )
        return self
