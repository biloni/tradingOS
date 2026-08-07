"""The 9-step decision pipeline (Revision Prompt 7):

1. Freeze evidence cutoff — `bundle.evidence_cutoff`, set by the caller
   before this function is ever called (Revision Prompt 4 discipline).
2. Validate instrument, market calendar, event timing, provider
   health — `pre_flight_veto_inputs`, the subset of the 10 hard vetoes
   (`services/hard_vetoes.py`) that can be evaluated before any
   committee runs. Any one firing publishes an explicit `NO_ACTION`
   recommendation immediately and stops — no committee call, no cost.
3. Calculate deterministic features — Revision Prompt 5's services,
   already computed by the caller into `bundle`.
4. Select the lane — `lane`, an explicit caller decision (the two
   committees "must not share a conclusion," so this pipeline never
   guesses which one applies).
5. Run the appropriate committee — `services/committee_orchestrator.run_committee()`.
6. Apply lane-specific eligibility and vetoes — already enforced inside
   `run_committee()` (the deterministic-veto override, ADR-051); nothing
   new needed here.
7. Apply portfolio, cash, sector, correlation, liquidity, and
   event-risk constraints — `services/position_sizing.py`'s six
   sequential caps (Tactical lane only, HES-3) plus a second hard-veto
   pass (`post_sizing_veto_inputs`) covering concurrent-trade limits.
8. Calculate the proposal — `services/position_sizing.py`'s resulting
   quantity/notional becomes an `OrderProposal`/`OrderProposalVersion`
   (R3 schema), never a broker call.
9. Publish a versioned recommendation or explicit `NO_ACTION` — always
   exactly one of: a `Recommendation` with a real action, a
   `Recommendation` with `NO_ACTION`, or (pre-flight veto) a `NO_ACTION`
   recommendation with no committee session at all.

The Investment lane stops after step 6 — this revision does not
calculate an investment order's size ("the AI workflow may recommend;
it may not calculate size or submit an order" applies to the pipeline
as much as to the committees; a real investment order-sizing model is a
future, explicitly out-of-scope phase, matching `InvestmentCioOutput`'s
own `proposed_max_allocation_pct` being a *proposed* ceiling, not a
computed share count)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    OrderProposalStatus,
    OrderSide,
    OrderType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationStatus,
)
from tradingos_api.models.enums import RecommendationMode as ModelsRecommendationMode
from tradingos_api.models.order_authority import OrderProposal, OrderProposalVersion
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.services.committee_orchestrator import (
    CommitteeInputBundle,
    CommitteeRunResult,
    run_committee,
)
from tradingos_api.services.hard_vetoes import (
    HardVetoInputs,
    VetoResult,
    any_veto_triggered,
    evaluate_hard_vetoes,
    triggered_vetoes,
)
from tradingos_api.services.position_sizing import (
    DEFAULT_SLIPPAGE_BPS,
    PositionSizingResult,
    compute_tactical_position_size,
)

PipelineOutcome = Literal[
    "PUBLISHED_ACTION", "PUBLISHED_NO_ACTION_PRE_FLIGHT", "PUBLISHED_NO_ACTION_POST_SIZING"
]


@dataclass(frozen=True)
class TacticalSizingContext:
    """Every input `compute_tactical_position_size()` needs, plus what's
    needed to turn the result into a real `OrderProposal` — all
    caller-assembled (current portfolio/account state), matching this
    pipeline's own "pure function, caller gathers the inputs" boundary."""

    account_id: uuid.UUID
    account_equity: Decimal
    price: Decimal
    risk_budget_pct: Decimal
    expected_move_pct: Decimal
    max_position_pct: Decimal
    max_sector_pct: Decimal
    sector_current_notional: Decimal
    max_correlated_group_pct: Decimal
    correlated_group_current_notional: Decimal
    avg_daily_dollar_volume: Decimal
    max_liquidity_pct_of_adv: Decimal
    is_speculative_name: bool
    speculative_position_pct_cap: Decimal
    available_cash: Decimal
    risk_policy_version: str
    concurrent_earnings_trades: int
    max_concurrent_earnings_trades: int
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS


@dataclass
class PipelineResult:
    outcome: PipelineOutcome
    pre_flight_vetoes: list[VetoResult]
    committee_result: CommitteeRunResult | None = None
    post_sizing_vetoes: list[VetoResult] | None = None
    sizing_result: PositionSizingResult | None = None
    order_proposal: OrderProposal | None = None
    order_proposal_version: OrderProposalVersion | None = None
    recommendation: Recommendation | None = None
    recommendation_version: RecommendationVersion | None = None


def _publish_no_action(
    db: Session,
    bundle: CommitteeInputBundle,
    lane: RecommendationMode,
    vetoes: list[VetoResult],
    triggered_by: str,
) -> tuple[Recommendation, RecommendationVersion]:
    """Step 9's "explicit NO_ACTION" path when a pre-flight veto fires
    before any committee runs — `committee_session_id` stays `NULL`
    (there was no session), same nullable-by-design column
    `RecommendationVersion` already has."""
    recommendation = Recommendation(
        instrument_id=bundle.instrument_id,
        watchlist_item_id=bundle.watchlist_item_id,
        mode=ModelsRecommendationMode(lane.value),
        opened_at=datetime.now(UTC),
        status=RecommendationStatus.ACTIVE,
    )
    db.add(recommendation)
    db.flush()

    explanations = "; ".join(f"{v.veto_code}: {v.explanation}" for v in vetoes)
    version = RecommendationVersion(
        recommendation_id=recommendation.id,
        committee_session_id=None,
        version_number=1,
        action=RecommendationAction.NO_ACTION,
        lane_action="NO_ACTION",
        confidence=RecommendationConfidence.LOW,
        rationale=f"Pre-flight hard veto(s) triggered before any committee ran: {explanations}",
        deterministic_inputs_snapshot={"pre_flight_veto_codes": [v.veto_code for v in vetoes]},
        generated_at=datetime.now(UTC),
        horizon_days_min=None,
        horizon_days_max=None,
        review_date=None,
    )
    db.add(version)
    db.flush()
    return recommendation, version


def _create_order_proposal(
    db: Session,
    *,
    recommendation_version: RecommendationVersion,
    instrument_id: uuid.UUID,
    context: TacticalSizingContext,
    sizing: PositionSizingResult,
    evidence_cutoff: datetime,
) -> tuple[OrderProposal, OrderProposalVersion]:
    """Step 8 — never a broker call, matching "no broker calls yet." Only
    ever invoked from the Tactical branch of the pipeline, so `mode` is
    always `TACTICAL` here — this project's models use plain FK columns,
    not ORM relationships, so `mode` is passed down rather than
    navigated to from `recommendation_version`."""
    proposal = OrderProposal(
        recommendation_version_id=recommendation_version.id,
        account_id=context.account_id,
        instrument_id=instrument_id,
        mode=ModelsRecommendationMode.TACTICAL,
        side=OrderSide.BUY,
        status=OrderProposalStatus.DRAFT,
    )
    db.add(proposal)
    db.flush()
    now = datetime.now(UTC)
    version = OrderProposalVersion(
        order_proposal_id=proposal.id,
        version_number=1,
        order_type=OrderType.LIMIT,
        quantity=Decimal(sizing.final_quantity),
        limit_price=context.price,
        stop_price=None,
        max_notional=sizing.final_notional,
        rationale=(
            f"Sized from a {sizing.risk_budget_pct}% risk budget against a "
            f"{sizing.expected_move_pct}% expected move; binding constraint(s): "
            f"{', '.join(sizing.binding_constraint_keys) or 'none'}."
        ),
        outside_hours=False,
        attached_legs={},
        max_slippage_bps=sizing.slippage_bps,
        valid_from=now,
        expires_at=None,
        risk_policy_version=context.risk_policy_version,
        data_cutoff=evidence_cutoff,
        quote_observed_at=now,
        requires_approval=True,
    )
    db.add(version)
    db.flush()
    return proposal, version


def run_recommendation_pipeline(
    db: Session,
    *,
    lane: RecommendationMode,
    bundle: CommitteeInputBundle,
    pre_flight_veto_inputs: HardVetoInputs,
    llm: LLMProvider,
    cost_ceiling_usd: Decimal,
    per_call_timeout_seconds: float,
    triggered_by: str,
    tactical_sizing_context: TacticalSizingContext | None = None,
    post_sizing_veto_inputs: HardVetoInputs | None = None,
) -> PipelineResult:
    # Step 2: validate — pre-flight hard vetoes, before any committee runs.
    pre_flight = evaluate_hard_vetoes(pre_flight_veto_inputs)
    if any_veto_triggered(pre_flight):
        recommendation, version = _publish_no_action(
            db, bundle, lane, triggered_vetoes(pre_flight), triggered_by
        )
        return PipelineResult(
            outcome="PUBLISHED_NO_ACTION_PRE_FLIGHT",
            pre_flight_vetoes=pre_flight,
            recommendation=recommendation,
            recommendation_version=version,
        )

    # Steps 3-6: features (already in `bundle`), lane selection (given),
    # committee run, and the deterministic-veto override (inside
    # `run_committee()`, ADR-051).
    committee_result = run_committee(
        db,
        lane=lane,
        bundle=bundle,
        llm=llm,
        cost_ceiling_usd=cost_ceiling_usd,
        per_call_timeout_seconds=per_call_timeout_seconds,
        triggered_by=triggered_by,
    )

    tactical_actions_needing_a_proposal = {"TRADE_ENTER", "TRADE_ADD_CONFIRMED"}
    proposed_action = (
        committee_result.recommendation_version.lane_action
        if committee_result.recommendation_version is not None
        else None
    )
    if (
        lane == RecommendationMode.TACTICAL
        and tactical_sizing_context is not None
        and proposed_action in tactical_actions_needing_a_proposal
    ):
        assert committee_result.recommendation_version is not None  # implied by proposed_action
        # Step 7: portfolio/cash/sector/correlation/liquidity/event-risk
        # constraints — the six sequential caps plus a second hard-veto
        # pass (e.g. max-concurrent-earnings-trades).
        sizing = compute_tactical_position_size(
            account_equity=tactical_sizing_context.account_equity,
            risk_budget_pct=tactical_sizing_context.risk_budget_pct,
            expected_move_pct=tactical_sizing_context.expected_move_pct,
            price=tactical_sizing_context.price,
            max_position_pct=tactical_sizing_context.max_position_pct,
            max_sector_pct=tactical_sizing_context.max_sector_pct,
            sector_current_notional=tactical_sizing_context.sector_current_notional,
            max_correlated_group_pct=tactical_sizing_context.max_correlated_group_pct,
            correlated_group_current_notional=tactical_sizing_context.correlated_group_current_notional,
            avg_daily_dollar_volume=tactical_sizing_context.avg_daily_dollar_volume,
            max_liquidity_pct_of_adv=tactical_sizing_context.max_liquidity_pct_of_adv,
            is_speculative_name=tactical_sizing_context.is_speculative_name,
            speculative_position_pct_cap=tactical_sizing_context.speculative_position_pct_cap,
            available_cash=tactical_sizing_context.available_cash,
            slippage_bps=tactical_sizing_context.slippage_bps,
        )
        post_sizing = (
            evaluate_hard_vetoes(post_sizing_veto_inputs) if post_sizing_veto_inputs else []
        )
        if (
            any_veto_triggered(post_sizing)
            or tactical_sizing_context.concurrent_earnings_trades
            >= tactical_sizing_context.max_concurrent_earnings_trades
            or sizing.final_quantity <= 0
        ):
            return PipelineResult(
                outcome="PUBLISHED_NO_ACTION_POST_SIZING",
                pre_flight_vetoes=pre_flight,
                committee_result=committee_result,
                post_sizing_vetoes=post_sizing,
                sizing_result=sizing,
                recommendation=committee_result.recommendation,
                recommendation_version=committee_result.recommendation_version,
            )

        # Step 8: calculate and persist the order proposal.
        proposal, proposal_version = _create_order_proposal(
            db,
            recommendation_version=committee_result.recommendation_version,
            instrument_id=bundle.instrument_id,
            context=tactical_sizing_context,
            sizing=sizing,
            evidence_cutoff=bundle.evidence_cutoff,
        )
        return PipelineResult(
            outcome="PUBLISHED_ACTION",
            pre_flight_vetoes=pre_flight,
            committee_result=committee_result,
            post_sizing_vetoes=post_sizing,
            sizing_result=sizing,
            order_proposal=proposal,
            order_proposal_version=proposal_version,
            recommendation=committee_result.recommendation,
            recommendation_version=committee_result.recommendation_version,
        )

    # Investment lane, or a Tactical action that doesn't propose a new
    # entry (TRADE_HOLD/TRADE_WAIT/TRADE_AVOID/NO_ACTION/etc.) — the
    # recommendation itself is the published artifact; no order sizing.
    return PipelineResult(
        outcome="PUBLISHED_ACTION",
        pre_flight_vetoes=pre_flight,
        committee_result=committee_result,
        recommendation=committee_result.recommendation,
        recommendation_version=committee_result.recommendation_version,
    )
