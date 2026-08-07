"""Demo script for Revision Prompt 7 — the deterministic decision
pipeline end to end: an Investment case, a Tactical pre-earnings case
(with real position sizing and a real `OrderProposal`), a pre-flight
veto producing an explicit `NO_ACTION`, a Tactical post-confirmation
case gated by HES-6's no-averaging-down-after-an-adverse-gap rule, and
the gap-through-stop disclosure (HES-5).

Uses a fake, deterministic `LLMProvider` rather than real Anthropic
calls — Revision Prompt 6's own demo (`demo_prompt6.py`) already proved
live-API compatibility for the committee layer; this revision's new
value is the deterministic pipeline/sizing/veto logic sitting around
that committee, which is best demonstrated deterministically and
reproducibly (and at zero additional API cost) rather than re-proving
connectivity a second time.

Run with: `python -m tradingos_api.scripts.demo_prompt7`
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.execution import Account
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle, EvidenceItem
from tradingos_api.services.gap_risk import estimate_stop_fill_under_gap
from tradingos_api.services.hard_vetoes import HardVetoInputs
from tradingos_api.services.post_confirmation_gate import evaluate_post_confirmation_eligibility
from tradingos_api.services.post_earnings_confirmation import PostEarningsConfirmationResult
from tradingos_api.services.recommendation_pipeline import (
    TacticalSizingContext,
    run_recommendation_pipeline,
)


def _cio_args(lane: str, action: str, thesis: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "recommendation_lane": lane,
        "evidence_ids": ["ev-1"],
        "factual_claims": [{"claim": "Synthetic claim.", "evidence_ids": ["ev-1"]}],
        "deterministic_feature_ids": ["feat-1"],
        "thesis": thesis,
        "strongest_supporting_evidence": "Synthetic supporting evidence.",
        "strongest_contradictory_evidence": "Synthetic contradictory evidence.",
        "risks": ["Synthetic risk."],
        "missing_information": [],
        "invalidation_conditions": ["Synthetic invalidation condition."],
        "categorical_stance": "BULLISH",
        "evidence_completeness": "HIGH",
    }
    if lane == "INVESTMENT":
        common.update(
            action=action,
            horizon_days_min=180,
            horizon_days_max=365,
            review_date=date.today().isoformat(),
            valuation_context="Trading in line with sector median.",
            preferred_accumulation_zone="On pullbacks toward the 50-day moving average.",
            tranche_plan="Three equal tranches over 60 days.",
            proposed_max_allocation_pct="5.0",
            durable_catalysts=["New product cycle"],
            thesis_break_conditions=["Loses market share for 2 consecutive quarters"],
            portfolio_role="Core satellite holding.",
            why_investment_not_trade=(
                "Multi-year durability thesis, not a short-term catalyst trade."
            ),
            minority_opinion=None,
        )
    else:
        common.update(
            action=action,
            setup_and_event_phase="Pre-earnings, after-close report expected.",
            proposed_holding_window_days_min=1,
            proposed_holding_window_days_max=5,
            key_catalyst="Quarterly earnings report",
            gap_risk="Moderate — median prior gap is 6%.",
            liquidity_risk="Low — ADV exceeds $100M.",
            entry_invalidation="Price closes below the pre-earnings low.",
            minority_opinion=None,
        )
    return common


def _make_fake_llm(lane: str, action: str, thesis: str) -> Any:
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
            args = _cio_args(lane, action, thesis)
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

    return _FakeLLM()


def _make_bundle(
    instrument_id: Any, symbol: str, hard_veto_active: bool = False
) -> CommitteeInputBundle:
    now = datetime.now(UTC)
    return CommitteeInputBundle(
        instrument_id=instrument_id,
        symbol=symbol,
        as_of=now,
        evidence_cutoff=now,
        evidence=[EvidenceItem("ev-1", "NewsItem", "Synthetic earnings-adjacent evidence.")],
        deterministic_feature_ids=["feat-1"],
        deterministic_summary="Synthetic deterministic summary (tactical score 7/8).",
        hard_veto_active=hard_veto_active,
        hard_veto_reason="going-concern flag is set" if hard_veto_active else None,
    )


def main() -> None:
    db = SessionLocal()
    try:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == "MRVL"))
        if instrument is None:
            print("Seed data missing MRVL — run `tradingos-seed` first.")
            return

        no_veto = HardVetoInputs(has_stale_required_data=False)

        # --- 1. Investment case: INVEST_BUY, full plan persisted ---
        print("\n=== 1. INVESTMENT PIPELINE: MRVL ===")
        investment_result = run_recommendation_pipeline(
            db,
            lane=RecommendationMode.INVESTMENT,
            bundle=_make_bundle(instrument.id, "MRVL"),
            pre_flight_veto_inputs=no_veto,
            llm=_make_fake_llm("INVESTMENT", "INVEST_BUY", "Durable AI-infrastructure demand."),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="DEMO_PROMPT7",
        )
        print(f"outcome: {investment_result.outcome}")
        print(f"lane_action: {investment_result.recommendation_version.lane_action}")  # type: ignore[union-attr]

        # --- 2. Tactical pre-earnings case: TRADE_ENTER, real sizing + OrderProposal ---
        print("\n=== 2. TACTICAL PRE-EARNINGS PIPELINE: MRVL ===")
        account = db.scalar(select(Account).limit(1))
        sizing_context = (
            TacticalSizingContext(
                account_id=account.id,
                account_equity=Decimal("100000"),
                price=Decimal("75.00"),
                risk_budget_pct=Decimal("0.25"),
                expected_move_pct=Decimal("6.0"),
                max_position_pct=Decimal("15.00"),
                max_sector_pct=Decimal("25.00"),
                sector_current_notional=Decimal("0"),
                max_correlated_group_pct=Decimal("25.00"),
                correlated_group_current_notional=Decimal("0"),
                avg_daily_dollar_volume=Decimal("150_000_000"),
                max_liquidity_pct_of_adv=Decimal("1.0"),
                is_speculative_name=False,
                speculative_position_pct_cap=Decimal("5.00"),
                available_cash=Decimal("100000"),
                risk_policy_version="risk-policy-v1",
                concurrent_earnings_trades=1,
                max_concurrent_earnings_trades=3,
            )
            if account is not None
            else None
        )
        tactical_result = run_recommendation_pipeline(
            db,
            lane=RecommendationMode.TACTICAL,
            bundle=_make_bundle(instrument.id, "MRVL"),
            pre_flight_veto_inputs=no_veto,
            llm=_make_fake_llm("TACTICAL", "TRADE_ENTER", "Pre-earnings momentum setup."),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="DEMO_PROMPT7",
            tactical_sizing_context=sizing_context,
        )
        print(f"outcome: {tactical_result.outcome}")
        print(f"lane_action: {tactical_result.recommendation_version.lane_action}")  # type: ignore[union-attr]
        if tactical_result.sizing_result is not None:
            s = tactical_result.sizing_result
            print(f"  raw_risk_based_notional: {s.raw_risk_based_notional}")
            print(f"  final_notional: {s.final_notional}  final_quantity: {s.final_quantity}")
            print(f"  binding_constraints: {s.binding_constraint_keys}")
        if tactical_result.order_proposal_version is not None:
            v = tactical_result.order_proposal_version
            print(f"  OrderProposal created: quantity={v.quantity} limit_price={v.limit_price}")

        # --- 3. Pre-flight veto: explicit NO_ACTION, no committee call ---
        print("\n=== 3. PRE-FLIGHT VETO (unverified event timing): MRVL ===")
        veto_inputs = HardVetoInputs(
            has_stale_required_data=False,
            event_timing_verified=False,
            event_timing_category="DATE_UNCONFIRMED",
        )
        veto_result = run_recommendation_pipeline(
            db,
            lane=RecommendationMode.TACTICAL,
            bundle=_make_bundle(instrument.id, "MRVL"),
            pre_flight_veto_inputs=veto_inputs,
            llm=_make_fake_llm("TACTICAL", "TRADE_ENTER", "unused — pre-flight veto blocks this"),
            cost_ceiling_usd=Decimal("5.00"),
            per_call_timeout_seconds=30,
            triggered_by="DEMO_PROMPT7",
        )
        print(f"outcome: {veto_result.outcome}")
        print(f"lane_action: {veto_result.recommendation_version.lane_action}")  # type: ignore[union-attr]
        print(f"rationale: {veto_result.recommendation_version.rationale}")  # type: ignore[union-attr]

        # --- 4. Post-confirmation gate: HES-6 blocks an adverse-gap add-on ---
        print("\n=== 4. POST-CONFIRMATION GATE (HES-6): adverse gap ===")
        all_gates_pass = PostEarningsConfirmationResult(
            components=[],
            results_gate_passed=True,
            guidance_gate_passed=True,
            market_reaction_gate_passed=True,
            all_gates_passed=True,
        )
        adverse_gap_eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=all_gates_pass, gap_pct=Decimal("-3.0"), liquidity_passed=True
        )
        print(
            f"eligible: {adverse_gap_eligibility.eligible}  "
            f"reasons: {adverse_gap_eligibility.reasons}"
        )
        assert adverse_gap_eligibility.eligible is False, "HES-6 must block an adverse-gap add-on"

        print("\n=== 4b. POST-CONFIRMATION GATE: favorable gap, all gates pass ===")
        favorable_eligibility = evaluate_post_confirmation_eligibility(
            post_earnings_result=all_gates_pass, gap_pct=Decimal("4.0"), liquidity_passed=True
        )
        print(f"eligible: {favorable_eligibility.eligible}")
        if favorable_eligibility.eligible:
            post_confirmation_result = run_recommendation_pipeline(
                db,
                lane=RecommendationMode.TACTICAL,
                bundle=_make_bundle(instrument.id, "MRVL"),
                pre_flight_veto_inputs=no_veto,
                llm=_make_fake_llm(
                    "TACTICAL", "TRADE_ADD_CONFIRMED", "Post-confirmation add — beat and raised."
                ),
                cost_ceiling_usd=Decimal("5.00"),
                per_call_timeout_seconds=30,
                triggered_by="DEMO_PROMPT7_POST_CONFIRMATION",
            )
            print(f"  outcome: {post_confirmation_result.outcome}")
            print(
                f"  lane_action: {post_confirmation_result.recommendation_version.lane_action}"  # type: ignore[union-attr]
            )

        # --- 5. Gap-through-stop disclosure (HES-5) ---
        print("\n=== 5. GAP-THROUGH-STOP (HES-5) ===")
        gap_estimate = estimate_stop_fill_under_gap(
            stop_price=Decimal("71.25"),
            prior_close=Decimal("75.00"),
            gap_pct=Decimal("-8.0"),
            side="SELL_STOP",
        )
        print(f"gapped_through_stop: {gap_estimate.gapped_through_stop}")
        print(
            f"estimated_fill_price: {gap_estimate.estimated_fill_price} "
            f"(stop was {gap_estimate.stop_price})"
        )
        print(f"disclosure: {gap_estimate.disclosure}")

        db.commit()
        print("\nAll Prompt 7 demo recommendations/proposals persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
