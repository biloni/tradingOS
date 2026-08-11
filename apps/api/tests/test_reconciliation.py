"""Broker aggregate position reconciliation tests (Revision Prompt 8)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    LotLane,
    OrderSide,
    OrderStatus,
    OrderType,
    ReconciliationStatus,
)
from tradingos_api.models.execution import Account, Execution, Order
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.portfolio_accounting import apply_buy_execution
from tradingos_api.services.reconciliation import run_reconciliation


def _account(db_session: Session) -> Account:
    account = db_session.scalar(select(Account).limit(1))
    assert account is not None
    return account


def _instrument(db_session: Session) -> Instrument:
    inst = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None
    return inst


def _buy(db_session: Session, *, account_id, instrument_id, qty: Decimal) -> None:
    order = Order(
        account_id=account_id,
        instrument_id=instrument_id,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        status=OrderStatus.FILLED,
    )
    db_session.add(order)
    db_session.flush()
    execution = Execution(
        order_id=order.id, quantity=qty, price=Decimal("50.00"), executed_at=datetime.now(UTC)
    )
    db_session.add(execution)
    db_session.flush()
    apply_buy_execution(
        db_session,
        execution=execution,
        account_id=account_id,
        instrument_id=instrument_id,
        lane=LotLane.TACTICAL,
    )


class TestBrokerAggregateReconciliation:
    def test_matching_broker_quantity_reconciles_clean(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        run, _replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
        )
        assert run.overall_status == ReconciliationStatus.MATCHED

    def test_mismatched_broker_quantity_is_a_discrepancy(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        run, _replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(90)},
        )
        assert run.overall_status == ReconciliationStatus.DISCREPANCY

    def test_manual_account_with_no_broker_feed_always_matches(self, db_session: Session) -> None:
        """A `MANUAL` account has no broker to compare against — "nothing
        to reconcile" is never presented as a discrepancy."""
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        run, _replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions=None,
        )
        assert run.overall_status == ReconciliationStatus.MATCHED

    def test_broker_reported_position_with_no_internal_lots_is_a_discrepancy(
        self, db_session: Session
    ) -> None:
        """A position the broker reports but the system has no lots for
        at all is caught too, not just the reverse."""
        account = _account(db_session)
        instrument = _instrument(db_session)

        run, _replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(50)},
        )
        assert run.overall_status == ReconciliationStatus.DISCREPANCY


class TestReconciliationIdempotency:
    """Revision Prompt 16 idempotency review — reconciliation was the
    one confirmed clean gap: every call, replay or not, created a
    brand-new run/line set with no way to detect a duplicate."""

    def test_repeated_key_returns_the_original_run_not_a_duplicate(
        self, db_session: Session
    ) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        first, first_replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
            idempotency_key="test-key-1",
        )
        second, second_replayed = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            # Deliberately different broker figure — proves the second
            # call never re-executes, it just returns the first result.
            broker_reported_positions={instrument.id: Decimal(999)},
            idempotency_key="test-key-1",
        )

        assert first_replayed is False
        assert second_replayed is True
        assert second.id == first.id
        assert second.overall_status == first.overall_status

    def test_no_key_never_dedupes(self, db_session: Session) -> None:
        """Un-keyed calls (the pre-existing default) are unaffected —
        each is its own run, exactly as before this change."""
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        first, _ = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
        )
        second, _ = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
        )
        assert first.id != second.id

    def test_different_keys_are_independent_runs(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(db_session, account_id=account.id, instrument_id=instrument.id, qty=Decimal(100))

        first, _ = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
            idempotency_key="key-a",
        )
        second, _ = run_reconciliation(
            db_session,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: Decimal(100)},
            idempotency_key="key-b",
        )
        assert first.id != second.id
