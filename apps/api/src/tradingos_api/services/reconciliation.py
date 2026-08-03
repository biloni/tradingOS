from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.symbol import Symbol
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.schemas.reconciliation import ReconciliationRowOut
from tradingos_api.services.portfolio import get_derived_positions


def reconcile_positions(
    session: Session, portfolio_id: int, broker: PaperBrokerProvider
) -> list[ReconciliationRowOut]:
    """Phase 3's explicit reconciliation deliverable: compare our derived
    positions (from filled `PaperOrder` rows) against Alpaca's own
    paper-account position report. A nonzero discrepancy for a symbol means
    something diverged between our fill records and Alpaca's book."""
    our_positions = get_derived_positions(session, portfolio_id)
    symbols_by_id: dict[int, str] = {}
    if our_positions:
        symbols_by_id = {
            s.id: s.ticker
            for s in session.execute(
                select(Symbol).where(Symbol.id.in_(our_positions.keys()))
            ).scalars()
        }
    our_by_ticker = {
        symbols_by_id[symbol_id]: int(pos["quantity"]) for symbol_id, pos in our_positions.items()
    }

    alpaca_positions = broker.get_paper_positions()
    alpaca_by_ticker = {p["symbol"]: Decimal(p["qty"]) for p in alpaca_positions}

    rows = []
    for ticker in sorted(set(our_by_ticker) | set(alpaca_by_ticker)):
        our_qty = our_by_ticker.get(ticker, 0)
        alpaca_qty = alpaca_by_ticker.get(ticker, Decimal(0))
        rows.append(
            ReconciliationRowOut(
                ticker=ticker,
                our_quantity=our_qty,
                alpaca_quantity=alpaca_qty,
                discrepancy=Decimal(our_qty) - alpaca_qty,
            )
        )
    return rows
