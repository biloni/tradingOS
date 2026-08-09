"""Corporate action application tests (Revision Prompt 8) — split and
dividend math, and idempotency ("never double-adjust the same account
for the same action")."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    CorporateActionType,
    LotLane,
    OrderSide,
    OrderStatus,
    OrderType,
)
from tradingos_api.models.execution import Account, Execution, Order
from tradingos_api.models.market_evidence import CorporateAction
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.corporate_actions_apply import apply_dividend, apply_split
from tradingos_api.services.portfolio_accounting import apply_buy_execution, get_open_lots


def _account(db_session: Session) -> Account:
    account = db_session.scalar(select(Account).limit(1))
    assert account is not None
    return account


def _instrument(db_session: Session) -> Instrument:
    inst = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None
    return inst


def _buy(db_session: Session, *, account_id, instrument_id, qty: Decimal, price: Decimal) -> None:
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
        order_id=order.id, quantity=qty, price=price, executed_at=datetime.now(UTC)
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


class TestSplitApplication:
    def test_split_preserves_total_cost_basis(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("100.00"),
        )

        split = CorporateAction(
            instrument_id=instrument.id,
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2026, 3, 1),
            ratio=Decimal("2"),
            source="test",
            ingested_at=datetime.now(UTC),
        )
        db_session.add(split)
        db_session.flush()

        apply_split(
            db_session, corporate_action=split, account_id=account.id, applied_at=datetime.now(UTC)
        )

        lots = get_open_lots(db_session, account_id=account.id, instrument_id=instrument.id)
        assert len(lots) == 1
        assert lots[0].quantity_remaining == Decimal(20)
        assert lots[0].cost_basis_price == Decimal("50.000000")
        # total cost basis (qty * price) is unchanged by the split
        assert lots[0].quantity_remaining * lots[0].cost_basis_price == Decimal(1000)

    def test_applying_the_same_split_twice_is_idempotent(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("100.00"),
        )

        split = CorporateAction(
            instrument_id=instrument.id,
            action_type=CorporateActionType.SPLIT,
            ex_date=date(2026, 3, 1),
            ratio=Decimal("2"),
            source="test",
            ingested_at=datetime.now(UTC),
        )
        db_session.add(split)
        db_session.flush()

        apply_split(
            db_session, corporate_action=split, account_id=account.id, applied_at=datetime.now(UTC)
        )
        apply_split(
            db_session, corporate_action=split, account_id=account.id, applied_at=datetime.now(UTC)
        )

        lots = get_open_lots(db_session, account_id=account.id, instrument_id=instrument.id)
        assert lots[0].quantity_remaining == Decimal(20)  # not 40 — the second call was a no-op


class TestDividendApplication:
    def test_dividend_credits_cash_by_shares_times_amount(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(100),
            price=Decimal("50.00"),
        )

        dividend = CorporateAction(
            instrument_id=instrument.id,
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2026, 3, 1),
            amount=Decimal("0.50"),
            source="test",
            ingested_at=datetime.now(UTC),
        )
        db_session.add(dividend)
        db_session.flush()

        application = apply_dividend(
            db_session,
            corporate_action=dividend,
            account_id=account.id,
            applied_at=datetime.now(UTC),
        )
        assert application.cash_credit_amount == Decimal("50.00")

    def test_applying_the_same_dividend_twice_is_idempotent(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        _buy(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(100),
            price=Decimal("50.00"),
        )

        dividend = CorporateAction(
            instrument_id=instrument.id,
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date(2026, 3, 1),
            amount=Decimal("0.50"),
            source="test",
            ingested_at=datetime.now(UTC),
        )
        db_session.add(dividend)
        db_session.flush()

        first = apply_dividend(
            db_session,
            corporate_action=dividend,
            account_id=account.id,
            applied_at=datetime.now(UTC),
        )
        second = apply_dividend(
            db_session,
            corporate_action=dividend,
            account_id=account.id,
            applied_at=datetime.now(UTC),
        )
        assert first.id == second.id
