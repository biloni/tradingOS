"""Demo script for Revision Prompt 10 — paper broker execution,
approval queue, and bracket lifecycle. Uses the deterministic
`SyntheticPaperBrokerProvider` throughout (not real Alpaca) so the demo
is reproducible without network access or credentials, exactly matching
this project's synthetic-fixture-provider pattern (Revision Prompt 4).

Demonstrates:
1. The full manual-approval order flow: propose -> policy-evaluate ->
   approve -> refresh -> submit -> fill -> reconcile.
2. A duplicate-click resubmit returning the same result, not a second
   fill.
3. An emulated bracket order (stop-loss + take-profit legs, since the
   synthetic broker does not support native brackets) with its
   reliability disclosure.
4. A kill-switch activation invalidating a still-pending approval.
5. A disabled-by-default paper auto-policy being explicitly enabled,
   then gating an automatic submission.

Run with: `python -m tradingos_api.scripts.demo_prompt10`
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import (
    AccountType,
    BrokerSubmissionOutcome,
    LotLane,
    OrderApprovalStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    StrategyFamily,
    TimeInForce,
)
from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    OrderApproval,
    OrderProposal,
    OrderProposalVersion,
    PaperAutoPolicyVersion,
)
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.order_authority import OrderAuthorityMode, OrderConfirmation
from tradingos_api.providers.synthetic_market_quote import SyntheticMarketQuoteProvider
from tradingos_api.providers.synthetic_paper_broker import (
    SyntheticBrokerCapabilityProvider,
    SyntheticPaperBrokerProvider,
)
from tradingos_api.services.bracket_execution import submit_bracket_order
from tradingos_api.services.hard_vetoes import HardVetoInputs, evaluate_hard_vetoes
from tradingos_api.services.order_authority import (
    BoundFieldsSnapshot,
    activate_kill_switch,
    compute_bound_fields_hash,
    deactivate_kill_switch,
)
from tradingos_api.services.order_execution import submit_paper_order
from tradingos_api.services.paper_auto_policy import (
    evaluate_auto_submission,
    get_active_auto_policy,
    to_auto_policy_grant,
)
from tradingos_api.services.reconciliation import run_reconciliation

_REFERENCE_PRICE = Decimal("150.00")


def _make_approval(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    side: OrderSide,
    quantity: Decimal,
    order_type: OrderType,
    limit_price: Decimal | None,
    quote_price_at_approval: Decimal,
    expires_in: timedelta = timedelta(hours=1),
) -> tuple[OrderApproval, ApprovalBoundFields]:
    now = datetime.now(UTC)
    rec = Recommendation(
        instrument_id=instrument.id, mode=RecommendationMode.TACTICAL, opened_at=now
    )
    db.add(rec)
    db.flush()
    rec_version = RecommendationVersion(
        recommendation_id=rec.id,
        version_number=1,
        action=RecommendationAction.BUY,
        lane_action="TRADE_ENTER",
        confidence=RecommendationConfidence.MEDIUM,
        rationale="demo fixture",
        generated_at=now,
        deterministic_inputs_snapshot={},
    )
    db.add(rec_version)
    db.flush()
    proposal = OrderProposal(
        recommendation_version_id=rec_version.id,
        account_id=account.id,
        instrument_id=instrument.id,
        mode=RecommendationMode.TACTICAL,
        side=side,
    )
    db.add(proposal)
    db.flush()
    proposal_version = OrderProposalVersion(
        order_proposal_id=proposal.id,
        version_number=1,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
    )
    db.add(proposal_version)
    db.flush()
    snapshot = BoundFieldsSnapshot(
        account_id=account.id,
        instrument_id=instrument.id,
        side=side.value,
        quantity=quantity,
        order_type=order_type.value,
        limit_price=limit_price,
        stop_price=None,
        time_in_force=TimeInForce.DAY.value,
        outside_hours=False,
        attached_legs={},
        max_notional=None,
        recommendation_version_id=rec_version.id,
    )
    approval = OrderApproval(
        order_proposal_version_id=proposal_version.id,
        approved_by="demo",
        requested_at=now,
        decided_at=now,
        expires_at=now + expires_in,
        status=OrderApprovalStatus.APPROVED,
        integrity_hash=compute_bound_fields_hash(snapshot),
    )
    db.add(approval)
    db.flush()
    bound_fields = ApprovalBoundFields(
        order_approval_id=approval.id,
        account_id=account.id,
        instrument_id=instrument.id,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        time_in_force=TimeInForce.DAY,
        outside_hours=False,
        attached_legs={},
        recommendation_version_id=rec_version.id,
        quote_price_at_approval=quote_price_at_approval,
    )
    db.add(bound_fields)
    db.flush()
    return approval, bound_fields


def _confirmation(account: Account) -> OrderConfirmation:
    return OrderConfirmation(
        confirmed_at=datetime.now(UTC),
        account_id=str(account.id),
        environment="PAPER",
        broker_endpoint="synthetic",
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
            name="Prompt 10 Demo Paper Account",
            owner_user_id=user.id,
        )
        db.add(account)
        db.flush()

        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": _REFERENCE_PRICE})
        capabilities = SyntheticBrokerCapabilityProvider().get_capabilities()
        quote_provider = SyntheticMarketQuoteProvider(reference_prices={"AMD": _REFERENCE_PRICE})

        print("=== 1. Manual-approval order flow: propose -> approve -> submit -> fill ===")
        approval, bound_fields = _make_approval(
            db,
            account=account,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Decimal(10),
            order_type=OrderType.MARKET,
            limit_price=None,
            quote_price_at_approval=_REFERENCE_PRICE,
        )
        result = submit_paper_order(
            db,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            confirmation=_confirmation(account),
            auto_policy=None,
            broker=broker,
            broker_base_url="https://paper-api.alpaca.markets",
            quote_provider=quote_provider,
            kill_switch_active=False,
            lane=LotLane.TACTICAL,
        )
        assert result.attempt.outcome == BrokerSubmissionOutcome.SUCCEEDED
        assert result.order is not None and result.order.status == OrderStatus.FILLED
        print(
            f"  order {result.order.id} FILLED at {_REFERENCE_PRICE}, "
            f"attempt {result.attempt.outcome.value}"
        )

        print("\n=== 2. Duplicate click — resubmitting the same approval is a no-op ===")
        duplicate_result = submit_paper_order(
            db,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            confirmation=_confirmation(account),
            auto_policy=None,
            broker=broker,
            broker_base_url="https://paper-api.alpaca.markets",
            quote_provider=quote_provider,
            kill_switch_active=False,
        )
        assert duplicate_result.attempt.id == result.attempt.id
        assert duplicate_result.order is not None and duplicate_result.order.id == result.order.id
        print(
            f"  same attempt {duplicate_result.attempt.id} returned — broker was not called again"
        )

        print("\n=== 3. Broker/local reconciliation ===")
        run = run_reconciliation(
            db,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(10)},
        )
        print(f"  reconciliation status: {run.overall_status.value}")
        assert run.overall_status.value == "MATCHED"

        print("\n=== 4. Emulated bracket order (stop-loss + take-profit, disclosed) ===")
        bracket_approval, bracket_bound_fields = _make_approval(
            db,
            account=account,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Decimal(5),
            order_type=OrderType.MARKET,
            limit_price=None,
            quote_price_at_approval=_REFERENCE_PRICE,
        )
        bracket_result = submit_bracket_order(
            db,
            approval=bracket_approval,
            bound_fields=bracket_bound_fields,
            account=account,
            instrument=instrument,
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            confirmation=_confirmation(account),
            auto_policy=None,
            broker=broker,
            capabilities=capabilities,
            broker_base_url="https://paper-api.alpaca.markets",
            quote_provider=quote_provider,
            kill_switch_active=False,
            lane=LotLane.TACTICAL,
            take_profit_price=Decimal("165.00"),
            stop_loss_price=Decimal("140.00"),
            emulation_acknowledged=True,
        )
        print(f"  used_native_bracket={bracket_result.used_native_bracket}")
        print(f"  primary order {bracket_result.primary.order.id} FILLED")  # type: ignore[union-attr]
        print(f"  stop-loss leg order: {bracket_result.stop_loss_order_id}")
        print(f"  take-profit leg order: {bracket_result.take_profit_order_id}")
        print(f"  disclosure shown: {bracket_result.disclosure_shown}")

        print("\n=== 5. Kill switch invalidates a still-pending approval ===")
        pending_approval, _pending_bound_fields = _make_approval(
            db,
            account=account,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Decimal(3),
            order_type=OrderType.MARKET,
            limit_price=None,
            quote_price_at_approval=_REFERENCE_PRICE,
        )
        pending_approval.status = OrderApprovalStatus.PENDING  # simulate not-yet-approved
        db.flush()
        event = activate_kill_switch(
            db,
            activated_by="demo",
            reason="demo: verify in-flight approvals are invalidated",
            now=datetime.now(UTC),
        )
        db.flush()
        db.refresh(pending_approval)
        print(f"  kill switch active={event.deactivated_at is None}")
        print(f"  previously-pending approval now: {pending_approval.status.value}")
        assert pending_approval.status == OrderApprovalStatus.INVALIDATED
        deactivate_kill_switch(db, event=event, now=datetime.now(UTC))
        db.flush()
        print("  kill switch deactivated")

        print("\n=== 6. Paper auto-policy: disabled by default, then explicitly enabled ===")
        assert get_active_auto_policy(db, owner_user_id=user.id) is None
        policy = PaperAutoPolicyVersion(
            owner_user_id=user.id,
            version_number=1,
            enabled=True,
            eligible_strategy_families=[StrategyFamily.EARNINGS_PRE_EVENT.value],
            min_score=Decimal(6),
            max_orders_per_day=3,
            max_daily_notional=Decimal("5000.00"),
            max_per_order_risk_pct=Decimal("0.0200"),
            allowed_time_windows=[{"start": "00:00", "end": "23:59"}],
            allowed_order_types=["MARKET", "LIMIT"],
            created_by="demo",
        )
        db.add(policy)
        db.flush()
        active_policy = get_active_auto_policy(db, owner_user_id=user.id)
        assert active_policy is not None
        grant = to_auto_policy_grant(active_policy)
        print(f"  active auto-policy version={grant.policy_version} enabled={grant.enabled}")

        eligibility = evaluate_auto_submission(
            db,
            policy=active_policy,
            strategy_family=StrategyFamily.EARNINGS_PRE_EVENT,
            score=Decimal(7),
            order_type_value="MARKET",
            proposed_notional=Decimal("1500.00"),
            per_order_risk_pct=Decimal("0.0100"),
            hard_veto_results=evaluate_hard_vetoes(HardVetoInputs(has_stale_required_data=False)),
        )
        print(f"  auto-submission eligible: {eligibility.eligible}")
        assert eligibility.eligible is True

        blocked_by_veto = evaluate_auto_submission(
            db,
            policy=active_policy,
            strategy_family=StrategyFamily.EARNINGS_PRE_EVENT,
            score=Decimal(7),
            order_type_value="MARKET",
            proposed_notional=Decimal("1500.00"),
            per_order_risk_pct=Decimal("0.0100"),
            hard_veto_results=evaluate_hard_vetoes(
                HardVetoInputs(has_stale_required_data=False, kill_switch_active=True)
            ),
        )
        print(
            f"  auto-submission eligible with an active hard veto: {blocked_by_veto.eligible} "
            f"({blocked_by_veto.failed_conditions})"
        )
        assert blocked_by_veto.eligible is False

        db.commit()
        print("\nAll Prompt 10 demo state persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
