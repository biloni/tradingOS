"""Demo script for Revision Prompt 11 — active position monitor and
post-earnings confirmation engine. Uses `SyntheticEarningsActualsProvider`
throughout (no real vendor exists for reported-results data yet, per
docs/PROVIDER_MATRIX.md) so the demo is reproducible without network
access or credentials.

Demonstrates:
1. Earnings-actuals ingestion, including a duplicate-release replay that
   does not create a second row.
2. A full eligible post-earnings confirmation: RESULTS_AVAILABLE and
   POST_EARNINGS_CONFIRMATION_READY alerts, the Tactical Trading Desk
   producing TRADE_ADD_CONFIRMED, a brand-new post-event recommendation
   identity, and a persisted `PostEarningsConfirmationSnapshot` (the
   confirmation-checklist screen's data source).
3. A results-beat-but-guidance-lowered case emitting GUIDANCE_CONFLICT.
4. A reversed intraday reaction invalidating the add (THESIS_INVALIDATED).
5. HES-6's absolute negative-gap rule failing the workflow
   (POST_EARNINGS_CONFIRMATION_FAILED) even with every other input
   otherwise unremarkable.
6. A worker-restart replay against each terminal run being a safe no-op.
7. The active position monitor: DATA_STALE, STOP_REACHED, GAP_RISK, and
   EARNINGS_APPROACHING against a real open position.

Run with: `python -m tradingos_api.scripts.demo_prompt11`
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import AccountType, AlertStatus
from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.market_evidence import EarningsConsensusSnapshot, EarningsGuidanceItem
from tradingos_api.models.market_evidence import EarningsEvent as EarningsEventModel
from tradingos_api.models.operations import Alert
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.providers.synthetic_evidence import SyntheticEarningsActualsProvider
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle, EvidenceItem
from tradingos_api.services.hard_vetoes import HardVetoInputs
from tradingos_api.services.ingest_evidence import ingest_earnings_actuals
from tradingos_api.services.position_monitor import PositionMonitorInputs, evaluate_position
from tradingos_api.services.post_earnings_workflow import (
    PostEarningsMarketContext,
    TacticalPipelineInputs,
    run_post_earnings_workflow,
)


class _FakeTacticalCioLLM:
    """Deterministic stand-in for the Tactical Trading Desk's CIO call —
    matches `tests/test_post_earnings_workflow.py`'s own fake exactly, so
    the demo and the test suite tell the same story about what a
    `TradingCioOutput`-shaped tool call must contain."""

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
        args: dict[str, Any] = {
            "agent_role": prompt_version,
            "prompt_version": prompt_version,
            "evidence_cutoff": datetime.now(UTC).isoformat(),
            "recommendation_lane": "TACTICAL",
            "evidence_ids": ["ev-1"],
            "factual_claims": [],
            "deterministic_feature_ids": ["feat-1"],
            "thesis": f"Synthetic {self._lane_action} case for the Prompt 11 demo.",
            "strongest_supporting_evidence": "N/A",
            "strongest_contradictory_evidence": "N/A",
            "risks": [],
            "missing_information": [],
            "invalidation_conditions": ["N/A"],
            "categorical_stance": "NEUTRAL",
            "evidence_completeness": "MEDIUM",
            "action": self._lane_action,
            "setup_and_event_phase": "N/A",
            "proposed_holding_window_days_min": 1,
            "proposed_holding_window_days_max": 5,
            "key_catalyst": "N/A",
            "gap_risk": "N/A",
            "liquidity_risk": "N/A",
            "entry_invalidation": "N/A",
            "minority_opinion": None,
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
            input_tokens=100,
            output_tokens=100,
        )


def _tactical_inputs(instrument_id: Any, event_id: Any, lane_action: str) -> TacticalPipelineInputs:
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
        llm=_FakeTacticalCioLLM(lane_action),
        cost_ceiling_usd=Decimal("5.00"),
        per_call_timeout_seconds=30,
        triggered_by="demo_prompt11",
    )


def _fresh_event(db: Session, instrument: Instrument, report_date: date) -> EarningsEventModel:
    event = EarningsEventModel(
        instrument_id=instrument.id,
        fiscal_period="Q3-2026",
        report_date=report_date,
        source="demo_fixture",
    )
    db.add(event)
    db.flush()
    return event


def _frozen_consensus(db: Session, event_id: Any) -> None:
    db.add(
        EarningsConsensusSnapshot(
            earnings_event_id=event_id,
            as_of=date(2026, 8, 25),
            consensus_eps=Decimal("1.1500"),
            consensus_revenue=Decimal("8200000000.00"),
            num_analysts=32,
            source="demo_fixture",
            observed_at=datetime(2026, 8, 25, tzinfo=UTC),
            usable_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
    )
    db.flush()


def _passing_market_context(
    *, gap_pct: Decimal, session_close: Decimal
) -> PostEarningsMarketContext:
    return PostEarningsMarketContext(
        gap_pct=gap_pct,
        session_open=Decimal("100"),
        session_close=session_close,
        has_intraday_capability=False,
        range_30min_pct=None,
        range_60min_pct=None,
        price_vs_vwap_pct=None,
        day_volume=None,
        baseline_avg_volume=None,
        instrument_return_pct=gap_pct,
        sector_return_pct=Decimal("1.0"),
        market_return_pct=Decimal("0.5"),
        liquidity_passed=True,
    )


def main() -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(UserProfile))
        assert user is not None, "run the seed script first (tradingos-seed)"
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert instrument is not None

        account = Account(
            account_type=AccountType.PAPER_ALPACA,
            name="Prompt 11 Demo Paper Account",
            owner_user_id=user.id,
        )
        db.add(account)
        db.flush()

        provider = SyntheticEarningsActualsProvider()

        print("=== 1. Earnings actuals ingestion + duplicate-release idempotency ===")
        event = _fresh_event(db, instrument, date(2026, 8, 13))
        first = ingest_earnings_actuals(
            db, provider, earnings_event_id=event.id, ticker="AMD", fiscal_period="Q3-2026"
        )
        second = ingest_earnings_actuals(
            db, provider, earnings_event_id=event.id, ticker="AMD", fiscal_period="Q3-2026"
        )
        print(f"  first ingestion: {len(first)} rows; replay: {len(second)} rows (no duplicates)")

        print(
            "\n=== 2. Eligible confirmation: RESULTS_AVAILABLE -> READY -> TRADE_ADD_CONFIRMED ==="
        )
        _frozen_consensus(db, event.id)
        db.add(
            EarningsGuidanceItem(
                earnings_event_id=event.id,
                metric="revenue",
                guidance_low=Decimal("8300000000.00"),
                guidance_high=Decimal("8500000000.00"),
                guidance_midpoint=Decimal("8400000000.00"),
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="demo_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db.flush()
        confirmed_now = datetime.now(UTC) + timedelta(hours=1)
        confirmed_result = run_post_earnings_workflow(
            db,
            owner_user_id=user.id,
            earnings_event_id=event.id,
            instrument_id=instrument.id,
            account_id=account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=provider,
            now=confirmed_now,
            market_context=_passing_market_context(
                gap_pct=Decimal("3.0"), session_close=Decimal("105")
            ),
            tactical_pipeline_inputs=_tactical_inputs(
                instrument.id, event.id, "TRADE_ADD_CONFIRMED"
            ),
        )
        print(f"  status: {confirmed_result.run.status.value}")
        print(f"  detail: {confirmed_result.run.detail}")
        print(
            f"  post_event_recommendation_id: {confirmed_result.run.post_event_recommendation_id}"
        )
        assert confirmed_result.run.status.value == "CONFIRMED"

        print("\n=== 3. Worker-restart replay against a terminal run is a safe no-op ===")
        replay = run_post_earnings_workflow(
            db,
            owner_user_id=user.id,
            earnings_event_id=event.id,
            instrument_id=instrument.id,
            account_id=account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=provider,
            now=confirmed_now,
        )
        print(f"  same run id: {replay.run.id == confirmed_result.run.id}")
        print(f"  status unchanged: {replay.run.status == confirmed_result.run.status}")

        print("\n=== 4. Results beat but guidance lowered -> GUIDANCE_CONFLICT ===")
        conflict_event = _fresh_event(db, instrument, date(2026, 11, 12))
        _frozen_consensus(db, conflict_event.id)
        db.add(
            EarningsGuidanceItem(
                earnings_event_id=conflict_event.id,
                metric="revenue",
                guidance_midpoint=Decimal("7900000000.00"),  # below the 8.2B consensus
                units="USD",
                period="Q4-2026",
                issued_at=datetime.now(UTC),
                source="demo_fixture",
                usable_at=datetime.now(UTC),
            )
        )
        db.flush()
        run_post_earnings_workflow(
            db,
            owner_user_id=user.id,
            earnings_event_id=conflict_event.id,
            instrument_id=instrument.id,
            account_id=account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=provider,
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(
                gap_pct=Decimal("3.0"), session_close=Decimal("105")
            ),
        )
        conflict_alerts = db.scalars(
            select(Alert).where(
                Alert.instrument_id == instrument.id, Alert.alert_type == "GUIDANCE_CONFLICT"
            )
        ).all()
        print(f"  GUIDANCE_CONFLICT alerts recorded: {len(conflict_alerts)}")

        print("\n=== 5. Reversed intraday reaction invalidates the add (THESIS_INVALIDATED) ===")
        reversal_event = _fresh_event(db, instrument, date(2026, 11, 13))
        _frozen_consensus(db, reversal_event.id)
        reversal_result = run_post_earnings_workflow(
            db,
            owner_user_id=user.id,
            earnings_event_id=reversal_event.id,
            instrument_id=instrument.id,
            account_id=account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=provider,
            now=datetime.now(UTC) + timedelta(hours=1),
            # Gap up, but the session closes below the open — a reversal.
            market_context=_passing_market_context(
                gap_pct=Decimal("3.0"), session_close=Decimal("95")
            ),
        )
        print(f"  status: {reversal_result.run.status.value}")
        print(f"  reversal_detected: {reversal_result.run.reversal_detected}")
        assert reversal_result.run.status.value == "INVALIDATED"

        print("\n=== 6. HES-6: a negative gap fails the workflow even with a real beat ===")
        veto_event = _fresh_event(db, instrument, date(2026, 11, 14))
        _frozen_consensus(db, veto_event.id)
        veto_result = run_post_earnings_workflow(
            db,
            owner_user_id=user.id,
            earnings_event_id=veto_event.id,
            instrument_id=instrument.id,
            account_id=account.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
            actuals_provider=provider,
            now=datetime.now(UTC) + timedelta(hours=1),
            market_context=_passing_market_context(
                gap_pct=Decimal("-2.0"), session_close=Decimal("98")
            ),
        )
        print(f"  status: {veto_result.run.status.value}")
        print(f"  detail: {veto_result.run.detail}")
        assert veto_result.run.status.value == "FAILED"
        assert "HES-6" in (veto_result.run.detail or "")

        print("\n=== 7. Active position monitor: stale data, stop reached, gap risk, earnings ===")
        stale_inputs = PositionMonitorInputs(
            account_id=account.id,
            instrument_id=instrument.id,
            owner_user_id=user.id,
            ticker="AMD",
            now=datetime.now(UTC),
            quote_price=Decimal("150.00"),
            quote_observed_at=None,
            position_quantity=Decimal("100"),
            upcoming_earnings_date=datetime.now(UTC).date() + timedelta(days=2),
        )
        monitor_result = evaluate_position(db, stale_inputs)
        print(
            "  DATA_STALE + EARNINGS_APPROACHING fired: "
            f"{sorted(a.alert_type.value for a, _ in monitor_result.alerts)}"
        )

        gap_inputs = PositionMonitorInputs(
            account_id=account.id,
            instrument_id=instrument.id,
            owner_user_id=user.id,
            ticker="AMD",
            now=datetime.now(UTC),
            quote_price=Decimal("90.00"),
            quote_observed_at=datetime.now(UTC),
            position_quantity=Decimal("100"),
            stop_price=Decimal("100.00"),
            prior_close=Decimal("105.00"),
        )
        gap_result = evaluate_position(db, gap_inputs)
        gap_alert_types = sorted(a.alert_type.value for a, _ in gap_result.alerts)
        print(f"  GAP_RISK + STOP_REACHED fired: {gap_alert_types}")

        open_alert_count = db.scalar(
            select(Alert)
            .where(Alert.instrument_id == instrument.id, Alert.status == AlertStatus.OPEN)
            .with_only_columns(Alert.id)
        )
        print(f"\n  (at least one open alert now on record: {open_alert_count is not None})")

        db.commit()
        print("\nAll Prompt 11 demo state persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
