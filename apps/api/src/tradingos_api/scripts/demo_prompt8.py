"""Demo script for Revision Prompt 8 — a symbol (MRVL) held
simultaneously as an Investment thesis and a Tactical earnings trade:
combined vs. per-lane subpositions, holding guidance for each lane, a
partial tactical exit that leaves the investment lot untouched, a
dividend corporate action, a broker reconciliation run, and the trade
journal view.

Run with: `python -m tradingos_api.scripts.demo_prompt8`
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import SessionLocal
from tradingos_api.models.enums import (
    CorporateActionType,
    LotLane,
    OrderSide,
    OrderStatus,
    OrderType,
    ReconciliationStatus,
)
from tradingos_api.models.execution import Account, Execution, Order, Trade
from tradingos_api.models.market_evidence import CorporateAction
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.corporate_actions_apply import apply_dividend
from tradingos_api.services.holding_guidance import (
    get_investment_holding_guidance,
    get_tactical_holding_guidance,
)
from tradingos_api.services.lane_attribution import (
    describe_lot_selection_certainty,
    get_combined_position_view,
)
from tradingos_api.services.portfolio_accounting import (
    apply_buy_execution,
    apply_sell_execution,
    get_cash_balance,
    get_open_lots,
)
from tradingos_api.services.reconciliation import run_reconciliation
from tradingos_api.services.trade_journal import get_journal_entry_view


def _make_execution(
    db: Session,
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
    db.add(order)
    db.flush()
    execution = Execution(
        order_id=order.id, quantity=qty, price=price, executed_at=datetime.now(UTC)
    )
    db.add(execution)
    db.flush()
    return execution


def main() -> None:
    db = SessionLocal()
    try:
        account = db.scalar(select(Account).limit(1))
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == "MRVL"))
        assert account is not None and instrument is not None

        starting_cash = get_cash_balance(
            db, account_id=account.id, starting_cash=account.starting_cash
        )
        print(f"Starting cash: {starting_cash}")

        # --- 1. Open an Investment lot (long-term thesis) ---
        print("\n=== 1. OPEN INVESTMENT LOT: MRVL ===")
        buy_investment = _make_execution(
            db,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(50),
            price=Decimal("60.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db,
            execution=buy_investment,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.INVESTMENT,
        )
        print("Opened 50 shares @ $60.00 in the INVESTMENT lane.")

        # --- 2. Open a Tactical lot (pre-earnings trade) ---
        print("\n=== 2. OPEN TACTICAL LOT: MRVL (earnings trade) ===")
        buy_tactical = _make_execution(
            db,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(100),
            price=Decimal("75.00"),
            side=OrderSide.BUY,
        )
        apply_buy_execution(
            db,
            execution=buy_tactical,
            account_id=account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
        )
        print("Opened 100 shares @ $75.00 in the TACTICAL lane.")

        # --- 3. Combined vs. per-lane subpositions ---
        print("\n=== 3. COMBINED VS. SUBPOSITIONS ===")
        view = get_combined_position_view(db, account_id=account.id, instrument_id=instrument.id)
        print(
            f"Combined (what a broker statement shows): {view.combined_quantity} shares "
            f"@ avg {view.combined_avg_cost}"
        )
        for lane, sub in view.subpositions.items():
            print(
                f"  {lane.value}: {sub.quantity} shares @ {sub.avg_cost} ({sub.lot_count} lot(s))"
            )

        # --- 4. Holding guidance per lane ---
        print("\n=== 4. HOLDING GUIDANCE ===")
        today = date.today()
        for lot in get_open_lots(
            db, account_id=account.id, instrument_id=instrument.id, lane=LotLane.INVESTMENT
        ):
            g = get_investment_holding_guidance(db, lot=lot, as_of=today)
            print(
                f"  INVESTMENT lot {lot.id}: action={g.current_action} "
                f"weight%={g.portfolio_weight_pct}"
            )
        for lot in get_open_lots(
            db, account_id=account.id, instrument_id=instrument.id, lane=LotLane.TACTICAL
        ):
            t = get_tactical_holding_guidance(db, lot=lot, as_of=today)
            print(
                f"  TACTICAL lot {lot.id}: action={t.current_action} "
                f"entry={t.entry_price} stop={t.stop_price}"
            )

        # --- 5. Partial tactical exit — investment lot untouched ---
        print("\n=== 5. PARTIAL TACTICAL EXIT (investment lot must remain untouched) ===")
        sell = _make_execution(
            db,
            account_id=account.id,
            instrument_id=instrument.id,
            qty=Decimal(60),
            price=Decimal("82.00"),
            side=OrderSide.SELL,
        )
        result = apply_sell_execution(
            db,
            execution=sell,
            account_id=account.id,
            instrument_id=instrument.id,
            target_lane=LotLane.TACTICAL,
        )
        print(f"Sold 60 tactical shares @ $82.00 -> realized P&L {result.realized_pnl}")
        print(f"Trade closed: {result.trade_closed}  {describe_lot_selection_certainty(result)}")

        view_after = get_combined_position_view(
            db, account_id=account.id, instrument_id=instrument.id
        )
        for lane, sub in view_after.subpositions.items():
            print(f"  {lane.value}: {sub.quantity} shares remaining")
        assert view_after.subpositions[LotLane.INVESTMENT].quantity == Decimal(50), (
            "investment lot must be untouched"
        )

        # --- 6. Corporate action: dividend ---
        print("\n=== 6. DIVIDEND CORPORATE ACTION ===")
        dividend = CorporateAction(
            instrument_id=instrument.id,
            action_type=CorporateActionType.DIVIDEND,
            ex_date=date.today(),
            amount=Decimal("0.25"),
            source="demo",
            ingested_at=datetime.now(UTC),
        )
        db.add(dividend)
        db.flush()
        application = apply_dividend(
            db, corporate_action=dividend, account_id=account.id, applied_at=datetime.now(UTC)
        )
        print(f"Dividend of $0.25/share credited ${application.cash_credit_amount} to cash.")

        # --- 7. Broker reconciliation ---
        print("\n=== 7. RECONCILIATION ===")
        combined_qty = get_combined_position_view(
            db, account_id=account.id, instrument_id=instrument.id
        ).combined_quantity
        run = run_reconciliation(
            db,
            account_id=account.id,
            as_of=datetime.now(UTC),
            broker_reported_positions={instrument.id: combined_qty},
        )
        print(f"Reconciliation status: {run.overall_status.value}")
        assert run.overall_status == ReconciliationStatus.MATCHED

        # --- 8. Trade journal view for the tactical trade ---
        print("\n=== 8. TRADE JOURNAL (TACTICAL) ===")
        tactical_trade = db.scalar(
            select(Trade).where(
                Trade.account_id == account.id,
                Trade.instrument_id == instrument.id,
                Trade.lane == LotLane.TACTICAL,
            )
        )
        assert tactical_trade is not None
        journal_view = get_journal_entry_view(db, trade=tactical_trade)
        print(
            f"  lane={journal_view.lane} status={journal_view.status.value} "
            f"outcome={journal_view.outcome}"
        )
        print(
            f"  realized_pnl={journal_view.realized_pnl} "
            f"recommendation_outcome={journal_view.recommendation_outcome}"
        )

        db.commit()
        print("\nAll Prompt 8 demo state persisted.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
