"""Demo script for Revision Prompt 5 — runs the deterministic tactical
score, expected-move calculation, baseline eligibility gate, investment-
quality engine, and post-earnings confirmation gates against two
synthetic scenarios (one eligible, one rejected), persists each as a
`FeatureComponentResult`-backed snapshot, and prints a human-readable
summary. Read-only against the seed data; writes only new, additive
snapshot/component rows — no recommendation or order is created ("do
not create recommendations yet").

Run with: `python -m tradingos_api.scripts.demo_prompt5`
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.baseline_eligibility import evaluate_baseline_eligibility
from tradingos_api.services.earnings_score import compute_tactical_earnings_score
from tradingos_api.services.expected_move import compute_expected_move
from tradingos_api.services.investment_quality import compute_investment_quality
from tradingos_api.services.persist_feature_results import (
    persist_investment_quality,
    persist_post_earnings_confirmation,
    persist_tactical_score,
)
from tradingos_api.services.post_earnings_confirmation import compute_post_earnings_confirmation


def _rising_closes(n: int, start: Decimal = Decimal(100)) -> list[Decimal | None]:
    return [start + Decimal(i) * Decimal("0.6") for i in range(n)]


def _falling_closes(n: int, start: Decimal = Decimal(200)) -> list[Decimal | None]:
    return [start - Decimal(i) * Decimal("0.6") for i in range(n)]


def _print_tactical(label: str, ticker: str, score: object, eligibility: object) -> None:
    print(f"\n=== {label}: {ticker} ===")
    print(f"tactical score: {score.total_score}/{score.max_score}")  # type: ignore[attr-defined]
    for c in score.components:  # type: ignore[attr-defined]
        print(f"  {c.component_key:24s} {c.status:22s} value={c.value} {c.detail or ''}")
    print(f"baseline eligible: {eligibility.eligible}")  # type: ignore[attr-defined]
    for cond in eligibility.conditions:  # type: ignore[attr-defined]
        mark = "PASS" if cond.passed else "FAIL"
        print(f"  {cond.condition_key:32s} {mark}  {cond.detail}")


def main() -> None:
    db = SessionLocal()
    try:
        events = {
            ticker: event_id
            for event_id, ticker in db.execute(
                select(EarningsEvent.id, Instrument.ticker).join(
                    Instrument, EarningsEvent.instrument_id == Instrument.id
                )
            ).all()
        }
        instruments = {row.ticker: row.id for row in db.scalars(select(Instrument)).all()}
        if "MRVL" not in events or "AMD" not in events:
            print("Seed data missing MRVL/AMD earnings events — run `tradingos-seed` first.")
            return

        now = datetime.now(UTC)

        # --- Scenario 1: ELIGIBLE synthetic earnings event ---
        eligible_score = compute_tactical_earnings_score(
            instrument_closes=_rising_closes(40),
            spy_closes=_rising_closes(40, start=Decimal(400)),
            instrument_volumes=[1_000_000 + i * 25_000 for i in range(25)],
            consensus_eps_estimate=Decimal("1.35"),
            prior_year_actual_eps=Decimal("1.10"),
            num_analysts=7,
            prior_gap_pcts=[Decimal("2.0"), Decimal("3.5"), Decimal("1.0")],
            as_of=date.today(),
        )
        eligible_move = compute_expected_move(
            atr_based_move_pct=Decimal("3.2"),
            prior_gap_abs_pcts=[Decimal("5.0"), Decimal("4.5"), Decimal("6.0")],
            option_implied_move_pct=Decimal("6.5"),
            option_implied_available=True,
        )
        eligible_gate = evaluate_baseline_eligibility(
            direction_score=eligible_score.total_score,
            expected_move_pct=eligible_move.selected_expected_move_pct,
            avg_daily_dollar_volume=Decimal("120_000_000"),
            num_analyst_estimates=7,
            timing_category="AFTER_CLOSE",
            evidence_is_fresh=True,
            has_portfolio_capacity=True,
            has_sector_capacity=True,
            has_unresolved_data_quality_issue=False,
        )
        _print_tactical("ELIGIBLE", "MRVL", eligible_score, eligible_gate)
        persist_tactical_score(
            db,
            earnings_event_id=events["MRVL"],
            as_of=now,
            evidence_cutoff=now,
            result=eligible_score,
        )

        # --- Scenario 2: REJECTED synthetic earnings event ---
        rejected_score = compute_tactical_earnings_score(
            instrument_closes=_falling_closes(40),
            spy_closes=_rising_closes(40, start=Decimal(400)),
            instrument_volumes=[900_000 - i * 10_000 for i in range(25)],
            consensus_eps_estimate=Decimal("0.60"),
            prior_year_actual_eps=Decimal("0.70"),
            num_analysts=2,
            prior_gap_pcts=[Decimal("-1.5")],
            as_of=date.today(),
        )
        rejected_move = compute_expected_move(
            atr_based_move_pct=Decimal("1.8"),
            prior_gap_abs_pcts=[Decimal("2.0")],
            option_implied_move_pct=None,
            option_implied_available=False,
        )
        rejected_gate = evaluate_baseline_eligibility(
            direction_score=rejected_score.total_score,
            expected_move_pct=rejected_move.selected_expected_move_pct,
            avg_daily_dollar_volume=Decimal("8_000_000"),
            num_analyst_estimates=2,
            timing_category="DATE_UNCONFIRMED",
            evidence_is_fresh=False,
            has_portfolio_capacity=True,
            has_sector_capacity=True,
            has_unresolved_data_quality_issue=True,
        )
        _print_tactical("REJECTED", "AMD", rejected_score, rejected_gate)
        persist_tactical_score(
            db,
            earnings_event_id=events["AMD"],
            as_of=now,
            evidence_cutoff=now,
            result=rejected_score,
        )

        # --- Investment lane: one healthy, deterministic component set ---
        if "MRVL" in instruments:
            investment_result = compute_investment_quality(
                revenue_growth_yoy_pct=Decimal("18.0"),
                earnings_growth_yoy_pct=Decimal("22.0"),
                margin_trend_bps_yoy=Decimal("40"),
                debt_to_equity=Decimal("0.6"),
                free_cash_flow_positive=True,
                pe_ratio=Decimal("28"),
                sector_median_pe=Decimal("30"),
                peg_ratio=Decimal("1.4"),
                earnings_revision_direction="UP",
                sector_name="Semiconductors",
                instrument_closes=_rising_closes(260),
                benchmark_closes=_rising_closes(260, start=Decimal(400)),
                documented_catalyst_count=3,
                has_major_unresolved_event_risk=False,
                position_pct_of_portfolio=Decimal("4.0"),
                sector_concentration_pct=Decimal("18.0"),
                max_position_pct=Decimal("5.0"),
                max_sector_pct=Decimal("25.0"),
                has_going_concern_flag=False,
                has_unresolved_data_quality_issue=False,
                as_of=date.today(),
            )
            print("\n=== INVESTMENT QUALITY: MRVL ===")
            print(f"hard_disqualified: {investment_result.hard_disqualified}")
            for c in investment_result.components:
                print(f"  {c.component_key:28s} {c.status:14s} value={c.value}")
            persist_investment_quality(
                db,
                instrument_id=instruments["MRVL"],
                as_of=date.today(),
                evidence_cutoff=now,
                result=investment_result,
            )

        # --- Post-earnings confirmation: MRVL's clean beat-and-raise ---
        confirmation_result = compute_post_earnings_confirmation(
            actual_eps=Decimal("1.45"),
            estimate_eps=Decimal("1.35"),
            actual_revenue=Decimal("1_600_000_000"),
            estimate_revenue=Decimal("1_550_000_000"),
            new_guidance_midpoint=Decimal("1.55"),
            prior_guidance_midpoint=Decimal("1.40"),
            consensus_midpoint=Decimal("1.45"),
            gap_pct=Decimal("4.5"),
            session_open=Decimal("104.5"),
            session_close=Decimal("108.0"),
            has_intraday_capability=False,
            range_30min_pct=None,
            range_60min_pct=None,
            price_vs_vwap_pct=None,
            day_volume=15_000_000,
            baseline_avg_volume=9_000_000,
            instrument_return_pct=Decimal("4.5"),
            sector_return_pct=Decimal("1.0"),
            market_return_pct=Decimal("0.5"),
        )
        print("\n=== POST-EARNINGS CONFIRMATION: MRVL ===")
        print(f"all_gates_passed: {confirmation_result.all_gates_passed}")
        for c in confirmation_result.components:
            print(f"  {c.component_key:28s} {c.status:22s} value={c.value}")
        persist_post_earnings_confirmation(
            db,
            earnings_event_id=events["MRVL"],
            as_of=now,
            evidence_cutoff=now,
            calculation_version="v1",
            result=confirmation_result,
        )

        db.commit()
        print("\nAll Prompt 5 demo snapshots persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
