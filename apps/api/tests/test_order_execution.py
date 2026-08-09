"""Order execution / broker-boundary tests (Revision Prompt 10) — the
11 required categories: bracket lifecycle, partial fill and partial
exit, rejection, accepted-order timeout, duplicate click, approval
expiration, quote changes outside tolerance, cancel/replace race, gap
through stop, broker/local reconciliation mismatch, and attempted live
configuration fails closed.

Every test builds its own minimal `OrderProposal -> OrderProposalVersion
-> OrderApproval -> ApprovalBoundFields` chain directly (bypassing the
router's own create/evaluate/approve endpoints, which are already
covered by `test_policy_order_authority.py`/the R3 approval tests) so
each scenario is isolated and fast."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AccountType,
    BrokerSubmissionOutcome,
    EnvironmentLabel,
    LotLane,
    OrderApprovalStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    TimeInForce,
)
from tradingos_api.models.execution import Account, Execution, Order, OrderLeg
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    BrokerSubmissionAttempt,
    OrderApproval,
    OrderProposal,
    OrderProposalVersion,
)
from tradingos_api.models.portfolio_ext import ReconciliationLine
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.order_authority import (
    OrderAuthorityDenied,
    OrderAuthorityMode,
    OrderConfirmation,
)
from tradingos_api.providers.broker import (
    BrokerSubmissionAmbiguous,
    PaperOrderRequest,
    PaperOrderResult,
)
from tradingos_api.providers.quotes_bars import MarketQuoteProvider, QuoteRecord
from tradingos_api.providers.synthetic_paper_broker import (
    SyntheticBrokerCapabilityProvider,
    SyntheticPaperBrokerProvider,
)
from tradingos_api.services.bracket_execution import (
    BracketEmulationNotAcknowledged,
    submit_bracket_order,
)
from tradingos_api.services.gap_risk import estimate_stop_fill_under_gap
from tradingos_api.services.order_authority import assert_broker_boundary_is_paper
from tradingos_api.services.order_execution import (
    cancel_order_at_broker,
    poll_and_reconcile_fills,
    submit_paper_order,
)
from tradingos_api.services.reconciliation import run_reconciliation

_APPROVED_FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


class _FixedQuote:
    def __init__(self, price: Decimal) -> None:
        self._price = price

    def get_latest_quote(self, ticker: str) -> QuoteRecord | None:
        return QuoteRecord(
            published_at=None,
            observed_at=datetime.now(UTC),
            source="test-fixture",
            ticker=ticker,
            price=str(self._price),
        )


def _paper_account(db: Session, owner_user_id: uuid.UUID) -> Account:
    account = Account(
        account_type=AccountType.PAPER_ALPACA,
        name=f"Test Paper {uuid.uuid4()}",
        owner_user_id=owner_user_id,
    )
    db.add(account)
    db.flush()
    return account


def _instrument(db: Session, ticker: str) -> Instrument:
    inst = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
    assert inst is not None
    return inst


def _make_approval(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal(10),
    order_type: OrderType = OrderType.MARKET,
    limit_price: Decimal | None = None,
    quote_price_at_approval: Decimal | None = None,
    attached_legs: dict[str, Any] | None = None,
    expires_at: datetime = _APPROVED_FAR_FUTURE,
    status: OrderApprovalStatus = OrderApprovalStatus.APPROVED,
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
        confidence=RecommendationConfidence.MEDIUM,
        rationale="test fixture",
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
    approval = OrderApproval(
        order_proposal_version_id=proposal_version.id,
        approved_by="test",
        requested_at=now,
        decided_at=now,
        expires_at=expires_at,
        status=status,
        integrity_hash="test-hash",
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
        attached_legs=attached_legs or {},
        recommendation_version_id=rec_version.id,
        quote_price_at_approval=quote_price_at_approval,
    )
    db.add(bound_fields)
    db.flush()
    return approval, bound_fields


def _submit(
    db: Session,
    *,
    approval: OrderApproval,
    bound_fields: ApprovalBoundFields,
    account: Account,
    instrument: Instrument,
    broker: Any,
    quote_provider: MarketQuoteProvider,
    **kwargs: Any,
) -> Any:
    return submit_paper_order(
        db,
        approval=approval,
        bound_fields=bound_fields,
        account=account,
        instrument=instrument,
        mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
        confirmation=OrderConfirmation(
            confirmed_at=datetime.now(UTC),
            account_id=str(account.id),
            environment="PAPER",
            broker_endpoint="synthetic",
        ),
        auto_policy=None,
        broker=broker,
        broker_base_url="https://paper-api.alpaca.markets",
        quote_provider=quote_provider,
        kill_switch_active=False,
        **kwargs,
    )


class TestBracketLifecycle:
    def test_emulated_bracket_submits_protective_legs_once_primary_fills(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})

        result = submit_bracket_order(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            confirmation=OrderConfirmation(
                confirmed_at=datetime.now(UTC),
                account_id=str(account.id),
                environment="PAPER",
                broker_endpoint="synthetic",
            ),
            auto_policy=None,
            broker=broker,
            capabilities=SyntheticBrokerCapabilityProvider().get_capabilities(),
            broker_base_url="https://paper-api.alpaca.markets",
            quote_provider=_FixedQuote(Decimal("150.00")),
            kill_switch_active=False,
            take_profit_price=Decimal("165.00"),
            stop_loss_price=Decimal("140.00"),
            emulation_acknowledged=True,
        )

        assert result.used_native_bracket is False
        assert result.disclosure_shown is True
        assert result.primary.order is not None
        assert result.primary.order.status == OrderStatus.FILLED
        assert result.stop_loss_order_id is not None
        assert result.take_profit_order_id is not None

        legs = db_session.scalars(
            select(OrderLeg).where(OrderLeg.bracket_group_id == result.bracket_group_id)
        ).all()
        roles = {leg.role.value for leg in legs}
        assert roles == {"PRIMARY", "STOP_LOSS", "TAKE_PROFIT"}
        assert len({leg.bracket_group_id for leg in legs}) == 1

    def test_emulation_requires_explicit_acknowledgment(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})

        with pytest.raises(BracketEmulationNotAcknowledged):
            submit_bracket_order(
                db_session,
                approval=approval,
                bound_fields=bound_fields,
                account=account,
                instrument=instrument,
                mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
                confirmation=OrderConfirmation(
                    confirmed_at=datetime.now(UTC),
                    account_id=str(account.id),
                    environment="PAPER",
                    broker_endpoint="synthetic",
                ),
                auto_policy=None,
                broker=broker,
                capabilities=SyntheticBrokerCapabilityProvider().get_capabilities(),
                broker_base_url="https://paper-api.alpaca.markets",
                quote_provider=_FixedQuote(Decimal("150.00")),
                kill_switch_active=False,
                take_profit_price=Decimal("165.00"),
                stop_loss_price=Decimal("140.00"),
                emulation_acknowledged=False,
            )

    def test_native_bracket_submits_one_order_with_one_primary_leg(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})
        native_capabilities = (
            SyntheticBrokerCapabilityProvider()
            .get_capabilities()
            .model_copy(update={"supports_native_brackets": True})
        )

        result = submit_bracket_order(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=OrderAuthorityMode.PAPER_MANUAL_APPROVAL,
            confirmation=OrderConfirmation(
                confirmed_at=datetime.now(UTC),
                account_id=str(account.id),
                environment="PAPER",
                broker_endpoint="synthetic",
            ),
            auto_policy=None,
            broker=broker,
            capabilities=native_capabilities,
            broker_base_url="https://paper-api.alpaca.markets",
            quote_provider=_FixedQuote(Decimal("150.00")),
            kill_switch_active=False,
            take_profit_price=Decimal("165.00"),
            stop_loss_price=Decimal("140.00"),
        )

        assert result.used_native_bracket is True
        assert result.disclosure_shown is False
        assert result.stop_loss_order_id is None
        assert result.take_profit_order_id is None
        legs = db_session.scalars(
            select(OrderLeg).where(OrderLeg.bracket_group_id == result.bracket_group_id)
        ).all()
        assert len(legs) == 1
        assert legs[0].role.value == "PRIMARY"


class TestPartialFillAndPartialExit:
    def test_a_resting_limit_order_books_only_the_new_fill_delta_each_poll(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            quantity=Decimal(10),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("140.00"),
        )
        broker = SyntheticPaperBrokerProvider()

        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("140.00")),
        )
        assert result.order is not None
        assert result.order.status == OrderStatus.SUBMITTED
        order_id = result.order.id
        broker_order_id = result.order.broker_order_id
        assert broker_order_id is not None

        broker.simulate_partial_fill(broker_order_id, Decimal("4"), Decimal("139.50"))
        order = db_session.get(Order, order_id)
        assert order is not None
        poll_and_reconcile_fills(
            db_session, order=order, broker=broker, lane=LotLane.TACTICAL, now=datetime.now(UTC)
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED
        booked = sum(
            (
                e.quantity
                for e in db_session.scalars(select(Execution).where(Execution.order_id == order_id))
            ),
            Decimal(0),
        )
        assert booked == Decimal("4")

        broker.simulate_partial_fill(broker_order_id, Decimal("6"), Decimal("139.00"))
        poll_and_reconcile_fills(
            db_session, order=order, broker=broker, lane=LotLane.TACTICAL, now=datetime.now(UTC)
        )
        assert order.status == OrderStatus.FILLED
        booked_total = sum(
            (
                e.quantity
                for e in db_session.scalars(select(Execution).where(Execution.order_id == order_id))
            ),
            Decimal(0),
        )
        assert booked_total == Decimal("10")
        assert (
            db_session.scalars(select(Execution).where(Execution.order_id == order_id))
            .all()
            .__len__()
            == 2
        )

    def test_partial_exit_consumes_only_the_sold_portion_of_the_open_lot(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        buy_approval, buy_bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Decimal(10),
        )
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})
        buy_result = _submit(
            db_session,
            approval=buy_approval,
            bound_fields=buy_bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
            lane=LotLane.TACTICAL,
        )
        assert buy_result.order is not None and buy_result.order.status == OrderStatus.FILLED

        sell_approval, sell_bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            side=OrderSide.SELL,
            quantity=Decimal(4),
        )
        sell_result = _submit(
            db_session,
            approval=sell_approval,
            bound_fields=sell_bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("155.00")),
            lane=LotLane.TACTICAL,
        )
        assert sell_result.order is not None and sell_result.order.status == OrderStatus.FILLED

        from tradingos_api.services.portfolio_accounting import get_open_lots

        remaining = get_open_lots(db_session, account_id=account.id, instrument_id=instrument.id)
        total_remaining = sum((lot.quantity_remaining for lot in remaining), Decimal(0))
        assert total_remaining == Decimal(6)


class TestRejection:
    def test_a_broker_rejection_is_recorded_as_failed_with_no_resulting_order(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = SyntheticPaperBrokerProvider(reject_symbols=frozenset({"AMD"}))

        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert result.order is None
        assert result.attempt.outcome == BrokerSubmissionOutcome.FAILED
        assert "rejected" in (result.attempt.detail or "").lower()


class _AmbiguousThenClearBroker:
    """A `PaperBrokerProvider` test double: the first `submit_paper_order()`
    call raises `BrokerSubmissionAmbiguous` (models a network timeout);
    `find_order_by_client_id()` returns `None` (the broker genuinely
    never received it), so a subsequent retry is safe and succeeds."""

    def __init__(self) -> None:
        self._real = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})
        self.submit_calls = 0

    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        self.submit_calls += 1
        if self.submit_calls == 1:
            raise BrokerSubmissionAmbiguous("simulated network timeout")
        return self._real.submit_paper_order(request)

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        return self._real.get_paper_order_status(broker_order_id)

    def find_order_by_client_id(self, client_order_id: str) -> PaperOrderResult | None:
        return self._real.find_order_by_client_id(client_order_id)

    def get_paper_positions(self) -> list[dict[str, str]]:
        return self._real.get_paper_positions()

    def cancel_paper_order(self, broker_order_id: str) -> None:
        self._real.cancel_paper_order(broker_order_id)


class _AmbiguousButActuallySucceededBroker(_AmbiguousThenClearBroker):
    """Models a timeout whose request *did* actually reach the broker —
    `find_order_by_client_id()` finds it, so no resubmit ever happens."""

    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        self.submit_calls += 1
        result = self._real.submit_paper_order(request)
        if self.submit_calls == 1:
            raise BrokerSubmissionAmbiguous("simulated network timeout after broker accepted it")
        return result


class TestAcceptedOrderTimeout:
    def test_an_ambiguous_timeout_is_resolved_by_querying_before_any_retry(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = _AmbiguousThenClearBroker()

        first = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert first.attempt.outcome == BrokerSubmissionOutcome.TIMEOUT_UNKNOWN
        assert first.order is None

        second = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert second.attempt.outcome == BrokerSubmissionOutcome.SUCCEEDED
        assert second.order is not None
        assert broker.submit_calls == 2

    def test_an_ambiguous_timeout_that_actually_succeeded_is_never_resubmitted(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = _AmbiguousButActuallySucceededBroker()

        first = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert first.attempt.outcome == BrokerSubmissionOutcome.TIMEOUT_UNKNOWN

        second = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert second.attempt.outcome == BrokerSubmissionOutcome.SUCCEEDED
        assert second.attempt.detail is not None and "resolved" in second.attempt.detail
        # Only the one real broker call from the first (ambiguous) attempt
        # — the retry resolved via find_order_by_client_id, never submitted again.
        assert broker.submit_calls == 1


class TestDuplicateClick:
    def test_a_second_submit_call_for_an_already_succeeded_approval_returns_the_same_order(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(db_session, account=account, instrument=instrument)
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})

        first = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        second = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
        )
        assert first.order is not None and second.order is not None
        assert first.order.id == second.order.id
        assert first.attempt.id == second.attempt.id
        attempts = db_session.scalars(
            select(BrokerSubmissionAttempt).where(
                BrokerSubmissionAttempt.order_approval_id == approval.id
            )
        ).all()
        assert len(attempts) == 1


class TestApprovalExpiration:
    def test_an_approval_past_its_expiry_cannot_be_submitted_even_if_still_marked_approved(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        broker = SyntheticPaperBrokerProvider()

        with pytest.raises(OrderAuthorityDenied, match="expired"):
            _submit(
                db_session,
                approval=approval,
                bound_fields=bound_fields,
                account=account,
                instrument=instrument,
                broker=broker,
                quote_provider=_FixedQuote(Decimal("150.00")),
            )

    def test_a_non_approved_status_is_rejected(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session, account=account, instrument=instrument, status=OrderApprovalStatus.PENDING
        )
        broker = SyntheticPaperBrokerProvider()

        with pytest.raises(OrderAuthorityDenied, match="PENDING"):
            _submit(
                db_session,
                approval=approval,
                bound_fields=bound_fields,
                account=account,
                instrument=instrument,
                broker=broker,
                quote_provider=_FixedQuote(Decimal("150.00")),
            )


class TestQuoteChangesOutsideTolerance:
    def test_a_large_price_move_since_approval_invalidates_rather_than_submits(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            quote_price_at_approval=Decimal("150.00"),
        )
        broker = SyntheticPaperBrokerProvider()

        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("170.00")),  # +13.3%, outside 1% tolerance
        )
        assert result.invalidated is True
        assert result.order is None
        assert approval.status == OrderApprovalStatus.INVALIDATED
        assert result.invalidation_reason is not None and "moved" in result.invalidation_reason

    def test_a_small_price_move_within_tolerance_still_submits(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            quote_price_at_approval=Decimal("150.00"),
        )
        broker = SyntheticPaperBrokerProvider()

        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.30")),  # +0.2%, within tolerance
        )
        assert result.invalidated is False
        assert result.order is not None


class TestCancelReplaceRace:
    def test_canceling_after_a_partial_fill_preserves_the_already_booked_quantity(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        """Models the race between a fill and a cancel arriving close
        together: whichever happened first at the broker, the local
        accounting must reflect only what was actually filled — never
        more (double-booked), never less (a lost fill)."""
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            quantity=Decimal(10),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("140.00"),
        )
        broker = SyntheticPaperBrokerProvider()
        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("140.00")),
        )
        order = result.order
        assert order is not None

        # A partial fill lands at the broker...
        broker.simulate_partial_fill(order.broker_order_id, Decimal("3"), Decimal("139.80"))
        # ...and a cancel request arrives moments later, racing it.
        cancel_order_at_broker(db_session, order=order, broker=broker)
        # The reconciliation poll still picks up the fill that happened
        # before the cancel took effect.
        poll_and_reconcile_fills(
            db_session, order=order, broker=broker, lane=LotLane.TACTICAL, now=datetime.now(UTC)
        )

        booked = sum(
            (
                e.quantity
                for e in db_session.scalars(select(Execution).where(Execution.order_id == order.id))
            ),
            Decimal(0),
        )
        assert booked == Decimal("3")
        assert order.canceled_at is not None


class TestGapThroughStop:
    def test_a_stop_loss_leg_filled_under_a_gap_books_the_gapped_price_not_the_nominal_stop(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        stop_price = Decimal("140.00")
        gap_estimate = estimate_stop_fill_under_gap(
            stop_price=stop_price, prior_close=Decimal("148.00"), gap_pct=Decimal("-8.0")
        )
        assert gap_estimate.gapped_through_stop is True
        assert gap_estimate.estimated_fill_price < stop_price
        assert "NOT a guaranteed execution price" in gap_estimate.disclosure

        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("148.00")})

        # Open the long position the stop-loss protects.
        buy_approval, buy_bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=Decimal(5),
        )
        buy_result = _submit(
            db_session,
            approval=buy_approval,
            bound_fields=buy_bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("148.00")),
            lane=LotLane.TACTICAL,
        )
        assert buy_result.order is not None and buy_result.order.status == OrderStatus.FILLED

        approval, bound_fields = _make_approval(
            db_session,
            account=account,
            instrument=instrument,
            side=OrderSide.SELL,
            quantity=Decimal(5),
            order_type=OrderType.STOP,
            limit_price=stop_price,
        )
        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(stop_price),
        )
        order = result.order
        assert order is not None
        # The gap carries the actual fill through the stop, worse than
        # the nominal stop price — exactly what the disclosure warns of.
        broker.simulate_fill(order.broker_order_id, Decimal(5), gap_estimate.estimated_fill_price)
        poll_and_reconcile_fills(
            db_session, order=order, broker=broker, lane=LotLane.TACTICAL, now=datetime.now(UTC)
        )
        execution = db_session.scalar(select(Execution).where(Execution.order_id == order.id))
        assert execution is not None
        assert execution.price == gap_estimate.estimated_fill_price
        assert execution.price != stop_price


class TestBrokerLocalReconciliationMismatch:
    def test_a_broker_reported_quantity_that_disagrees_with_local_lots_is_flagged(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session, account=account, instrument=instrument, quantity=Decimal(10)
        )
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})
        result = _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
            lane=LotLane.TACTICAL,
        )
        assert result.order is not None and result.order.status == OrderStatus.FILLED

        # The broker reports 7 shares (e.g. a corporate action or a
        # missed fill this app never ingested) instead of the 10 we
        # think we hold.
        run = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal("7")},
        )
        assert run.overall_status.value == "DISCREPANCY"
        lines = db_session.scalars(
            select(ReconciliationLine).where(ReconciliationLine.reconciliation_run_id == run.id)
        ).all()
        line = next(line for line in lines if line.instrument_id == instrument.id)
        assert line.internal_quantity == Decimal(10)
        assert line.broker_reported_quantity == Decimal("7")

    def test_a_matching_broker_report_reconciles_clean(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        account = _paper_account(db_session, seeded_user_id)
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session, account=account, instrument=instrument, quantity=Decimal(10)
        )
        broker = SyntheticPaperBrokerProvider(reference_prices={"AMD": Decimal("150.00")})
        _submit(
            db_session,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            broker=broker,
            quote_provider=_FixedQuote(Decimal("150.00")),
            lane=LotLane.TACTICAL,
        )
        run = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(10)},
        )
        assert run.overall_status.value == "MATCHED"


class TestAttemptedLiveConfigurationFailsClosed:
    def test_a_non_paper_account_type_is_refused(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="PAPER_ALPACA"):
            assert_broker_boundary_is_paper(
                account_type=AccountType.MANUAL,
                environment_label=EnvironmentLabel.PAPER,
                broker_base_url="https://paper-api.alpaca.markets",
            )

    def test_a_live_environment_label_is_refused(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="PAPER"):
            assert_broker_boundary_is_paper(
                account_type=AccountType.PAPER_ALPACA,
                environment_label=EnvironmentLabel.LIVE,
                broker_base_url="https://paper-api.alpaca.markets",
            )

    def test_a_live_broker_base_url_is_refused(self) -> None:
        with pytest.raises(OrderAuthorityDenied, match="paper"):
            assert_broker_boundary_is_paper(
                account_type=AccountType.PAPER_ALPACA,
                environment_label=EnvironmentLabel.PAPER,
                broker_base_url="https://api.alpaca.markets",
            )

    def test_submit_paper_order_never_reaches_the_broker_for_a_manual_account(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        manual_account = Account(
            account_type=AccountType.MANUAL,
            name=f"Test Manual {uuid.uuid4()}",
            owner_user_id=seeded_user_id,
        )
        db_session.add(manual_account)
        db_session.flush()
        instrument = _instrument(db_session, "AMD")
        approval, bound_fields = _make_approval(
            db_session, account=manual_account, instrument=instrument
        )
        broker = _AmbiguousThenClearBroker()  # any double with a call counter works here

        with pytest.raises(OrderAuthorityDenied):
            _submit(
                db_session,
                approval=approval,
                bound_fields=bound_fields,
                account=manual_account,
                instrument=instrument,
                broker=broker,
                quote_provider=_FixedQuote(Decimal("150.00")),
            )
        assert broker.submit_calls == 0


class TestBrokerBoundaryIsSingleEntryPoint:
    """OA-7: "only the deterministic order service can submit, replace,
    or cancel an order" — extended to Revision Prompt 10's real paper
    submission path. Mirrors `test_policy_order_authority.py`'s existing
    structural check for the Phase 8 fill-booking path."""

    def test_broker_protocol_methods_are_called_only_from_order_execution_module(self) -> None:
        import ast
        from pathlib import Path

        src_root = Path(__file__).resolve().parent.parent / "src" / "tradingos_api"
        broker_methods = {"submit_paper_order", "cancel_paper_order", "find_order_by_client_id"}
        offending: list[str] = []
        for py_file in src_root.rglob("*.py"):
            if py_file.parent.name == "providers":
                continue  # the Protocol/implementations themselves define these methods
            if py_file.name in ("order_execution.py",) and py_file.parent.name == "services":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in broker_methods:
                    offending.append(f"{py_file.relative_to(src_root)}::{node.attr}")
        assert offending == [], (
            f"a PaperBrokerProvider method is called outside "
            f"services/order_execution.py: {offending}"
        )
