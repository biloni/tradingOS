"""Demo script for Revision Prompt 6 — runs a real Investment Committee
(8 roles, live Anthropic calls, cost-ceiling bounded) and a real Tactical
Trading Desk (9 roles, live Anthropic calls) end to end against synthetic
evidence, then shows the side-by-side view. The deterministic-veto
override guarantee is demonstrated separately with a fake, deliberately
adversarial LLM (see `tests/test_committee_orchestrator.py` and
`tests/test_committee_prompt_injection.py`) rather than hoping a real
model happens to misbehave — that guarantee is a property of the code,
not of any particular model response, and asserting it against a live,
non-deterministic call would not actually prove anything stronger.

Run with: `python -m tradingos_api.scripts.demo_prompt6`
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import SessionLocal
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.anthropic_llm import AnthropicLLMProvider
from tradingos_api.services.committee_orchestrator import (
    CommitteeInputBundle,
    EvidenceItem,
    run_committee,
)
from tradingos_api.services.side_by_side import get_side_by_side_view

_COST_CEILING_USD = Decimal("0.75")
_PER_CALL_TIMEOUT_SECONDS = 45.0


def _print_run(label: str, result: Any) -> None:
    print(f"\n=== {label} ===")
    print(f"session status: {result.session.status.value}")
    total_cost = sum((rr.outcome.cost_usd for rr in result.role_runs), Decimal(0))
    for rr in result.role_runs:
        out = rr.outcome
        stance = getattr(out.output, "categorical_stance", None) if out.output else None
        action = getattr(out.output, "action", None) if out.output else None
        print(
            f"  {rr.role.display_name:34s} {out.status:10s} "
            f"stance={stance or '-':10s} action={action or '-':22s} "
            f"cost=${out.cost_usd:.4f} latency={out.latency_ms}ms"
        )
    print(f"  TOTAL COST: ${total_cost:.4f}")
    if result.recommendation_version is not None:
        print(f"  -> lane_action: {result.recommendation_version.lane_action}")
        print(f"  -> veto_override_applied: {result.veto_override_applied}")
        print(f"  -> rationale: {result.recommendation_version.rationale[:200]}")
    else:
        print("  -> no recommendation written (CIO run did not succeed)")


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set — this demo requires a real Anthropic key.")
        return
    llm = AnthropicLLMProvider(settings)

    db = SessionLocal()
    try:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == "MRVL"))
        if instrument is None:
            print("Seed data missing MRVL — run `tradingos-seed` first.")
            return

        now = datetime.now(UTC)

        # --- Investment Committee: real Anthropic calls, synthetic evidence ---
        investment_bundle = CommitteeInputBundle(
            instrument_id=instrument.id,
            symbol="MRVL",
            as_of=now,
            evidence_cutoff=now,
            evidence=[
                EvidenceItem(
                    "ev-1",
                    "NewsItem",
                    "MRVL reported data-center revenue up 20% YoY, driven by custom AI "
                    "silicon design wins with two hyperscale cloud customers.",
                ),
                EvidenceItem(
                    "ev-2",
                    "FundamentalsSnapshot",
                    "Trailing operating margin improved 150bps YoY; free cash flow positive "
                    "for the fourth consecutive quarter.",
                ),
            ],
            deterministic_feature_ids=["feat-revenue-growth-1", "feat-valuation-1"],
            deterministic_summary=(
                "REVENUE_EARNINGS_GROWTH: PASS (combined growth 40.0%); "
                "MARGIN_TREND: PASS (+150bps); BALANCE_SHEET_QUALITY: PASS "
                "(D/E 0.6, FCF positive); VALUATION: PASS (P/E 28 vs sector "
                "median 30); BUSINESS_SECTOR_DURABILITY: FAIL (Semiconductors "
                "is not in the versioned durable-sector set); "
                "hard_disqualified: False"
            ),
            hard_veto_active=False,
            hard_veto_reason=None,
        )
        investment_result = run_committee(
            db,
            lane=RecommendationMode.INVESTMENT,
            bundle=investment_bundle,
            llm=llm,
            cost_ceiling_usd=_COST_CEILING_USD,
            per_call_timeout_seconds=_PER_CALL_TIMEOUT_SECONDS,
            triggered_by="DEMO_PROMPT6",
        )
        db.commit()
        _print_run("INVESTMENT COMMITTEE (live Anthropic calls) — MRVL", investment_result)

        # --- Tactical Trading Desk: real Anthropic calls, synthetic evidence ---
        tactical_bundle = CommitteeInputBundle(
            instrument_id=instrument.id,
            symbol="MRVL",
            as_of=now,
            evidence_cutoff=now,
            evidence=[
                EvidenceItem(
                    "ev-3",
                    "EarningsEvent",
                    "MRVL reports Q3 earnings after the close in 3 trading days; consensus "
                    "EPS $1.35 vs $1.10 prior-year actual, 7 analyst estimates.",
                ),
                EvidenceItem(
                    "ev-4",
                    "MarketBar",
                    "MRVL is trading above its 20-day EMA with positive 20-day relative "
                    "strength versus SPY and rising 5-session average volume.",
                ),
            ],
            deterministic_feature_ids=["feat-tactical-score-1", "feat-expected-move-1"],
            deterministic_summary=(
                "Tactical 8-component score: 7/8 PASS (PRICE_ABOVE_EMA20, RS_20D_VS_SPY, "
                "MOMENTUM_5D, VOLUME_ACCUMULATION, FORECAST_EPS_GROWTH, ANALYST_COVERAGE, "
                "SPY_ABOVE_EMA20 all PASS; PRIOR_GAP_BIAS FAIL). Expected move: ATR 3.2%, "
                "historical median gap 5.0%, selected 5.0%. Baseline eligibility: ELIGIBLE "
                "(all 9 conditions pass)."
            ),
            hard_veto_active=False,
            hard_veto_reason=None,
        )
        tactical_result = run_committee(
            db,
            lane=RecommendationMode.TACTICAL,
            bundle=tactical_bundle,
            llm=llm,
            cost_ceiling_usd=_COST_CEILING_USD,
            per_call_timeout_seconds=_PER_CALL_TIMEOUT_SECONDS,
            triggered_by="DEMO_PROMPT6",
        )
        db.commit()
        _print_run("TACTICAL TRADING DESK (live Anthropic calls) — MRVL", tactical_result)

        # --- Side-by-side view ---
        view = get_side_by_side_view(db, instrument.id)
        print("\n=== SIDE-BY-SIDE: MRVL ===")
        print(f"Investment: {view.investment.lane_action if view.investment else None}")
        print(f"Tactical:   {view.tactical.lane_action if view.tactical else None}")
        print(f"\nDivergence explanation:\n{view.divergence_explanation}")

        print(
            "\n(The deterministic-veto override guarantee — a committee result cannot "
            "override a hard disqualification or a failed baseline-eligibility gate — is "
            "demonstrated deterministically in "
            "tests/test_committee_orchestrator.py::TestDeterministicVetoCannotBeOverridden "
            "and tests/test_committee_prompt_injection.py, using a fake, deliberately "
            "adversarial LLM. That is a stronger proof than a live call, which cannot be "
            "relied on to misbehave the same way twice.)"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
