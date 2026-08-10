"""Demo script for Revision Prompt 12 — performance, decision quality,
and recommendation-versus-reality analytics. Builds a real trade
history through `apply_execution()` (Revision Prompt 8's accounting
engine, not hand-constructed `Trade` rows) and real `MarketBar` history,
then walks through every new analytics surface against that state.

Demonstrates:
1. Portfolio-level metrics: equity curve, TWR/MWR, Sharpe/Sortino,
   drawdown/recovery, beta/alpha vs. SPY, trade stats.
2. Strategy-level breakdowns: lane contribution, pre-event vs.
   post-confirmation, score-band, sector, score-threshold sensitivity,
   policy veto outcomes — including the honest "0 sample" result for an
   unattributed manual fill.
3. Recommendation-vs-reality: a hypothetical fill simulation for an
   IGNORED recommendation, walked forward over real market bars.
4. Morning plan quality on an account with no morning-plan runs yet —
   the honest sparse-sample result, not a fabricated rate.
5. The AI coach's sample-size guardrail, live: called once against a
   fresh account (0 trades, LLM never invoked) and again after the
   trade history is built (adequate sample, LLM invoked through the
   same `run_agent_role()` guardrail every committee role uses).

Run with: `python -m tradingos_api.scripts.demo_prompt12`
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import (
    AccountType,
    LotLane,
    OrderSide,
    OrderStatus,
    OrderType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationLevelKind,
    RecommendationMode,
    RecommendationStatus,
    Timeframe,
)
from tradingos_api.models.execution import Account, Execution, Order
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.market_evidence import MarketBar
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationLevel,
    RecommendationVersion,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.services.morning_plan_quality import (
    get_approval_conversion,
    get_morning_plan_quality_summary,
    get_realized_results_by_section,
)
from tradingos_api.services.performance_coach import get_coach_summary
from tradingos_api.services.performance_portfolio import get_portfolio_performance
from tradingos_api.services.performance_strategy import (
    get_lane_contribution,
    get_policy_veto_outcomes,
    get_pre_event_vs_post_confirmation_contribution,
    get_results_by_score_band,
    get_results_by_sector,
    get_score_threshold_sensitivity,
)
from tradingos_api.services.portfolio_accounting import apply_execution
from tradingos_api.services.recommendation_reality import (
    compute_and_persist_hypothetical_outcome,
    get_recommendation_reality_rows,
)


class _FakeCoachLLM:
    """Deterministic stand-in for the coach's Anthropic call, matching
    `tests/test_performance_coach.py`'s own fake exactly."""

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
        args = {
            "summary_text": (
                "Based on 12 closed trades, the win rate and profit factor look "
                "favorable, but a 12-trade sample is still small — treat these "
                "figures as a preliminary read, not a stable edge."
            ),
            "key_observations": [
                "Sample size is 12 trades — below what most trading-statistics "
                "conventions consider a stable sample.",
                "Realized results skew positive across the trades taken so far.",
            ],
        }
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(tool_use_id="t1", tool_name="submit_agent_output", arguments=args)
            ],
            raw_content=[],
            input_tokens=450,
            output_tokens=90,
        )


def _seed_bars(
    db: Session, *, instrument: Instrument, start: date, days: int, closes: list[Decimal]
) -> None:
    current = start
    for close in closes[:days]:
        db.add(
            MarketBar(
                instrument_id=instrument.id,
                as_of=current,
                timeframe=Timeframe.DAILY,
                open=close,
                high=close * Decimal("1.01"),
                low=close * Decimal("0.99"),
                close=close,
                volume=1_000_000,
                source="demo_fixture",
                observed_at=datetime.combine(current, datetime.min.time(), tzinfo=UTC),
            )
        )
        current += timedelta(days=1)
    db.flush()


def _manual_fill(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    side: OrderSide,
    quantity: Decimal,
    price: Decimal,
    executed_at: datetime,
    lane: LotLane,
) -> Execution:
    order = Order(
        account_id=account.id,
        instrument_id=instrument.id,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        status=OrderStatus.FILLED,
    )
    db.add(order)
    db.flush()
    execution = Execution(
        order_id=order.id, quantity=quantity, price=price, executed_at=executed_at
    )
    db.add(execution)
    db.flush()
    apply_execution(
        db,
        execution=execution,
        account_id=account.id,
        instrument_id=instrument.id,
        side=side,
        lane=lane,
    )
    db.flush()
    return execution


def _round_trip(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    day: date,
    buy_price: Decimal,
    sell_price: Decimal,
    lane: LotLane,
) -> None:
    buy_at = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    sell_at = buy_at + timedelta(hours=6)
    _manual_fill(
        db,
        account=account,
        instrument=instrument,
        side=OrderSide.BUY,
        quantity=Decimal(10),
        price=buy_price,
        executed_at=buy_at,
        lane=lane,
    )
    _manual_fill(
        db,
        account=account,
        instrument=instrument,
        side=OrderSide.SELL,
        quantity=Decimal(10),
        price=sell_price,
        executed_at=sell_at,
        lane=lane,
    )


def main() -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(UserProfile))
        assert user is not None, "run the seed script first"
        amd = db.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        spy = db.scalar(select(Instrument).where(Instrument.ticker == "SPY"))
        assert amd is not None and spy is not None

        account = Account(
            account_type=AccountType.MANUAL, name="Prompt 12 Demo Account", owner_user_id=user.id
        )
        db.add(account)
        db.flush()

        start = date(2026, 5, 1)
        _seed_bars(
            db,
            instrument=amd,
            start=start,
            days=20,
            closes=[Decimal(v) for v in (100, 102, 101, 104, 106, 103, 108, 110, 107, 112,
                                          109, 114, 116, 113, 118, 120, 117, 122, 124, 121)],
        )
        _seed_bars(
            db,
            instrument=spy,
            start=start,
            days=20,
            closes=[Decimal(v) for v in (500, 501, 500, 503, 504, 503, 506, 507, 506, 509,
                                          508, 510, 512, 511, 513, 515, 514, 516, 518, 517)],
        )

        print("=== 1. AI coach guardrail BEFORE any trade history (0 trades) ===")
        empty_performance = get_portfolio_performance(
            db, account=account, as_of=start + timedelta(days=1)
        )
        pre_result = get_coach_summary(performance=empty_performance, llm=None)
        print(f"  is_sample_adequate: {pre_result.is_sample_adequate}")
        print(f"  sample_size: {pre_result.sample_size}")
        print(f"  narrative: {pre_result.narrative}")
        print(f"  message: {pre_result.insufficient_sample_message}")
        assert pre_result.is_sample_adequate is False
        assert pre_result.narrative is None

        print("\n=== 2. Building 12 closed round trips (mixed lanes, mixed outcomes) ===")
        outcomes = [
            (Decimal(100), Decimal(110)), (Decimal(102), Decimal(98)),
            (Decimal(101), Decimal(112)), (Decimal(104), Decimal(100)),
            (Decimal(106), Decimal(115)), (Decimal(103), Decimal(109)),
            (Decimal(108), Decimal(104)), (Decimal(110), Decimal(120)),
            (Decimal(107), Decimal(113)), (Decimal(112), Decimal(108)),
            (Decimal(109), Decimal(118)), (Decimal(114), Decimal(122)),
        ]
        for i, (buy_price, sell_price) in enumerate(outcomes):
            lane = LotLane.TACTICAL if i % 2 == 0 else LotLane.INVESTMENT
            _round_trip(
                db,
                account=account,
                instrument=amd,
                day=start + timedelta(days=i),
                buy_price=buy_price,
                sell_price=sell_price,
                lane=lane,
            )
        print(f"  {len(outcomes)} round trips recorded via apply_execution()")

        print("\n=== 3. Portfolio performance (return/risk/drawdown/benchmark) ===")
        as_of = start + timedelta(days=len(outcomes) + 1)
        performance = get_portfolio_performance(db, account=account, as_of=as_of)
        print(f"  equity: {performance.equity}")
        print(f"  realized_pnl: {performance.realized_pnl}")
        print(f"  trade_stats: num_trades={performance.trade_stats.num_trades}, "
              f"win_rate_pct={performance.trade_stats.win_rate_pct}, "
              f"profit_factor={performance.trade_stats.profit_factor}, "
              f"expectancy={performance.trade_stats.expectancy}")
        print(f"  sharpe_ratio: {performance.sharpe_ratio}")
        print(f"  sortino_ratio: {performance.sortino_ratio}")
        print(f"  max_drawdown_pct: {performance.drawdown.max_drawdown_pct}")
        print(f"  time_weighted_return_pct: {performance.time_weighted_return_pct}")
        print(f"  money_weighted_return_pct: {performance.money_weighted_return_pct}")
        print(
            f"  beta_vs_spy: {performance.beta_vs_spy}, "
            f"alpha_vs_spy_pct: {performance.alpha_vs_spy_pct}"
        )

        print("\n=== 4. Strategy breakdowns ===")
        lane_groups = get_lane_contribution(db, account_id=account.id)
        for g in lane_groups:
            print(
                f"  lane={g.group_key}: trades={g.stats.num_trades}, "
                f"win_rate={g.stats.win_rate_pct}"
            )
        pre_post_groups = get_pre_event_vs_post_confirmation_contribution(db, account_id=account.id)
        print(f"  pre/post-confirmation groups (all UNATTRIBUTED — no committee-linked "
              f"trades in this demo): {[g.group_key for g in pre_post_groups]}")
        score_groups = get_results_by_score_band(db, account_id=account.id)
        print(f"  score-band groups (honestly empty — no RecommendationAttribution "
              f"rows in this demo): {score_groups}")
        sector_groups = get_results_by_sector(db, account_id=account.id)
        print(f"  sector groups: {[(g.group_key, g.stats.num_trades) for g in sector_groups]}")
        sensitivity = get_score_threshold_sensitivity(
            db, account_id=account.id, thresholds=[4, 5, 6, 7]
        )
        print(f"  score-threshold sensitivity (all 0 sample — same reason): "
              f"{[(s.group_key, s.stats.num_trades) for s in sensitivity]}")
        vetoes = get_policy_veto_outcomes(db, account_id=account.id)
        print(f"  policy veto outcomes: total={vetoes.total_evaluations}, "
              f"authorized={vetoes.authorized}, denied={vetoes.denied}")

        print("\n=== 5. Recommendation-vs-reality: hypothetical fill for an IGNORED call ===")
        rec = Recommendation(
            instrument_id=amd.id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db.add(rec)
        db.flush()
        version = RecommendationVersion(
            recommendation_id=rec.id,
            version_number=1,
            action=RecommendationAction.BUY,
            lane_action="TRADE_ENTER",
            confidence=RecommendationConfidence.MEDIUM,
            score=Decimal("6.5"),
            rationale="Demo recommendation for the hypothetical-fill walkthrough.",
            generated_at=datetime.combine(start, datetime.min.time(), tzinfo=UTC),
        )
        db.add(version)
        db.flush()
        db.add_all(
            [
                RecommendationLevel(
                    recommendation_version_id=version.id,
                    kind=RecommendationLevelKind.ENTRY,
                    price=Decimal("101"),
                ),
                RecommendationLevel(
                    recommendation_version_id=version.id,
                    kind=RecommendationLevelKind.STOP,
                    price=Decimal("97"),
                ),
                RecommendationLevel(
                    recommendation_version_id=version.id,
                    kind=RecommendationLevelKind.TARGET,
                    price=Decimal("115"),
                ),
            ]
        )
        db.flush()
        hypothetical = compute_and_persist_hypothetical_outcome(
            db, recommendation=rec, recommendation_version_id=version.id
        )
        assert hypothetical is not None
        print(f"  simulated_exit_reason: {hypothetical.simulated_exit_reason}")
        print(f"  simulated_pnl_pct: {hypothetical.simulated_pnl_pct}")
        reality_rows = get_recommendation_reality_rows(db, account_id=account.id)
        demo_row = next(r for r in reality_rows if r.recommendation_id == rec.id)
        print(f"  reality row disposition: {demo_row.disposition}, "
              f"hypothetical_pnl_pct: {demo_row.hypothetical_pnl_pct}")

        print("\n=== 6. Morning plan quality (honest sparse result — no runs yet) ===")
        quality = get_morning_plan_quality_summary(db)
        print(f"  total_runs: {quality.total_runs}, on_time_rate_pct: {quality.on_time_rate_pct}, "
              f"complete_final_rate_pct: {quality.complete_final_rate_pct}")
        sections = get_realized_results_by_section(db)
        print(f"  realized-results-by-section groups: {len(sections)} (0 expected — no morning "
              f"plan items reference this demo's trades)")
        conversion = get_approval_conversion(db)
        print(f"  approval conversion: total_approvals={conversion.total_approvals}, "
              f"rate={conversion.approval_to_submission_rate_pct}")

        print("\n=== 7. AI coach guardrail AFTER building trade history (adequate sample) ===")
        adequate_result = get_coach_summary(performance=performance, llm=_FakeCoachLLM())
        print(f"  is_sample_adequate: {adequate_result.is_sample_adequate}")
        print(f"  sample_size: {adequate_result.sample_size}")
        assert adequate_result.is_sample_adequate is True
        assert adequate_result.narrative is not None
        print(f"  summary_text: {adequate_result.narrative.summary_text}")
        print(f"  key_observations: {adequate_result.narrative.key_observations}")
        print(f"  run_metadata: model={adequate_result.narrative.run_metadata.model}, "
              f"cost_usd={adequate_result.narrative.run_metadata.cost_usd}")

        db.commit()
        print("\nAll Prompt 12 demo state persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
