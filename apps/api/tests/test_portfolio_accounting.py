"""Core portfolio accounting engine tests (Revision Prompt 8) — "same
symbol with two lanes," "partial tactical exit while investment lot
remains," "lot-selection uncertainty disclosure," and "cash and
position invariants.\""""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import LotLane, OrderSide, OrderStatus, OrderType, TradeStatus
from tradingos_api.models.execution import Account, Execution, Order, Position, Trade
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.portfolio_accounting import (
    InsufficientLotsError,
    apply_buy_execution,
    apply_sell_execution,
    get_cash_balance,
    get_open_lots,
    get_subpositions_by_lane,
)


def _account(db_session: Session) -> Account:
    account = db_session.scalar(select(Account).limit(1))
    assert account is not None
    return account


def _instrument(db_session: Session) -> Instrument:
    inst = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None
    return inst


def _make_execution(
    db_session: Session,
    *,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    qty: Decimal,
    price: Decimal,
    side: OrderSide,
) -> Execution:
    order = Order(
        account_id=account_id,
        instrument_id=instrument_id,
        side=side,
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
    return execution


class TestSameSymbolTwoLanes:
    def test_investment_and_tactical_lots_coexist_independently(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)

        buy_tactical = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(100),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy_tactical,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        buy_investment = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(50),
            price=Decimal("60.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy_investment,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.INVESTMENT,
        )

        subpositions = get_subpositions_by_lane(
            db_session, account_id=account.id, instrument_id=instrument.id
        )
        assert subpositions[LotLane.TACTICAL].quantity == Decimal(100)
        assert subpositions[LotLane.INVESTMENT].quantity == Decimal(50)

        position = db_session.scalar(
            select(Position).where(
                Position.account_id == account.id, Position.instrument_id == instrument.id
            )
        )
        assert position is not None
        assert position.quantity == Decimal(150)

        trades = db_session.scalars(
            select(Trade).where(
                Trade.account_id == account.id, Trade.instrument_id == instrument.id
            )
        ).all()
        lanes_with_open_trades = {t.lane for t in trades if t.status == TradeStatus.OPEN}
        assert lanes_with_open_trades == {LotLane.TACTICAL, LotLane.INVESTMENT}


class TestPartialTacticalExitWhileInvestmentLotRemains:
    def test_selling_tactical_shares_never_touches_the_investment_lot(
        self, db_session: Session
    ) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)

        buy_tactical = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(100),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy_tactical,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        buy_investment = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(50),
            price=Decimal("60.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy_investment,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.INVESTMENT,
        )

        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(60),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        result = apply_sell_execution(
            db_session,
            execution=sell,
            account_id=account.id,
            instrument_id=instrument.id,
            target_lane=LotLane.TACTICAL,
        )

        assert result.realized_pnl == Decimal("300.000000")  # (55-50)*60
        assert result.trade_closed is False  # 40 remains in the tactical lane

        subpositions = get_subpositions_by_lane(
            db_session, account_id=account.id, instrument_id=instrument.id
        )
        assert subpositions[LotLane.TACTICAL].quantity == Decimal(40)
        assert subpositions[LotLane.INVESTMENT].quantity == Decimal(50)  # untouched

        investment_lots = get_open_lots(
            db_session, account_id=account.id, instrument_id=instrument.id, lane=LotLane.INVESTMENT
        )
        assert len(investment_lots) == 1
        assert investment_lots[0].quantity_remaining == Decimal(50)
        assert investment_lots[0].closed_at is None


class TestLotSelectionUncertaintyDisclosure:
    def test_sell_with_explicit_target_lane_is_certain(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        buy = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(5),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        result = apply_sell_execution(
            db_session,
            execution=sell,
            account_id=account.id,
            instrument_id=instrument.id,
            target_lane=LotLane.TACTICAL,
        )
        assert result.lane_selection_is_certain is True

    def test_sell_with_no_target_lane_is_disclosed_as_uncertain(self, db_session: Session) -> None:
        """Models a real broker fill that reports only a net quantity —
        the system cannot certainly say which lane it closed."""
        account = _account(db_session)
        instrument = _instrument(db_session)
        buy = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.UNCLASSIFIED,
        )
        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(5),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        result = apply_sell_execution(
            db_session,
            execution=sell,
            account_id=account.id,
            instrument_id=instrument.id,
            target_lane=None,
        )
        assert result.lane_selection_is_certain is False


class TestCashAndPositionInvariants:
    def test_cash_balance_reflects_buys_and_sells_exactly(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        starting_cash = get_cash_balance(
            db_session, account_id=account.id, starting_cash=account.starting_cash
        )

        buy = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        after_buy = get_cash_balance(
            db_session, account_id=account.id, starting_cash=account.starting_cash
        )
        assert after_buy == starting_cash - Decimal("500.00")

        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        apply_sell_execution(
            db_session,
            execution=sell,
            account_id=account.id,
            instrument_id=instrument.id,
            target_lane=LotLane.TACTICAL,
        )
        after_sell = get_cash_balance(
            db_session, account_id=account.id, starting_cash=account.starting_cash
        )
        assert after_sell == starting_cash - Decimal("500.00") + Decimal("550.00")

    def test_selling_more_than_is_open_fails_closed(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        buy = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(20),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        with pytest.raises(InsufficientLotsError):
            apply_sell_execution(
                db_session,
                execution=sell,
                account_id=account.id,
                instrument_id=instrument.id,
                target_lane=LotLane.TACTICAL,
            )

    def test_a_sell_never_borrows_from_a_different_lane(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        buy = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(10),
            price=Decimal("50.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db_session,
            execution=buy,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.INVESTMENT,
        )
        # No tactical lots exist at all — a tactical-targeted sell must fail,
        # not silently consume the investment lot instead.
        sell = _make_execution(
            db_session,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(5),
            price=Decimal("55.00"),
            side=OrderSide.SELL,
        )
        with pytest.raises(InsufficientLotsError):
            apply_sell_execution(
                db_session,
                execution=sell,
                account_id=account.id,
                instrument_id=instrument.id,
                target_lane=LotLane.TACTICAL,
            )
