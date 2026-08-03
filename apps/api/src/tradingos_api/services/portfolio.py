from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.paper_order import (
    PaperOrder,
    PaperOrderSide,
    PaperOrderStatus,
    PaperOrderType,
)
from tradingos_api.models.paper_portfolio import PaperPortfolio
from tradingos_api.models.symbol import Symbol
from tradingos_api.schemas.portfolio import PortfolioSnapshotOut, PositionOut
from tradingos_api.services.price_bars import get_latest_price_bars

FILLED_STATUSES = (PaperOrderStatus.FILLED, PaperOrderStatus.PARTIALLY_FILLED)
PRICE_LOOKBACK_DAYS = 10


class InsufficientCapitalError(ValueError):
    """Raised when a proposed BUY would overdraw cash (principle 1: preserve
    capital before pursuing returns)."""


class InsufficientPositionError(ValueError):
    """Raised when a proposed SELL exceeds the currently held quantity — no
    short selling in this MVP."""


def get_or_create_default_portfolio(session: Session) -> PaperPortfolio:
    """The MVP has exactly one paper portfolio; lazily created on first use
    rather than via a data-migration or seed script (ADR-013)."""
    portfolio = session.execute(select(PaperPortfolio).limit(1)).scalar_one_or_none()
    if portfolio is not None:
        return portfolio
    portfolio = PaperPortfolio(starting_cash_usd=Decimal("10000.00"), created_at=datetime.now(UTC))
    session.add(portfolio)
    session.commit()
    session.refresh(portfolio)
    return portfolio


def _get_filled_orders(session: Session, portfolio_id: int) -> list[PaperOrder]:
    stmt = select(PaperOrder).where(
        PaperOrder.portfolio_id == portfolio_id,
        PaperOrder.status.in_(FILLED_STATUSES),
    )
    return list(session.execute(stmt).scalars().all())


def get_derived_positions(
    session: Session, portfolio_id: int
) -> dict[int, dict[str, Decimal | int]]:
    """{symbol_id: {"quantity": int, "avg_entry_price": Decimal}} for every
    symbol with a nonzero net long position, derived from filled
    `PaperOrder` rows (PaperPosition is not a table — ADR-013). Cost basis
    is a simple weighted average across BUY fills, not FIFO/LIFO tax lots —
    a documented MVP simplification (ADR-013)."""
    orders = _get_filled_orders(session, portfolio_id)
    buckets: dict[int, dict[str, Decimal | int]] = {}
    for order in orders:
        if order.filled_quantity <= 0 or order.filled_avg_price is None:
            continue
        bucket = buckets.setdefault(
            order.symbol_id, {"quantity": 0, "buy_qty": 0, "buy_cost": Decimal(0)}
        )
        if order.side == PaperOrderSide.BUY:
            bucket["quantity"] = int(bucket["quantity"]) + order.filled_quantity
            bucket["buy_qty"] = int(bucket["buy_qty"]) + order.filled_quantity
            bucket["buy_cost"] = (
                Decimal(bucket["buy_cost"]) + order.filled_quantity * order.filled_avg_price
            )
        else:
            bucket["quantity"] = int(bucket["quantity"]) - order.filled_quantity

    result: dict[int, dict[str, Decimal | int]] = {}
    for symbol_id, bucket in buckets.items():
        quantity = int(bucket["quantity"])
        if quantity <= 0:
            continue
        buy_qty = int(bucket["buy_qty"])
        avg_entry = Decimal(bucket["buy_cost"]) / buy_qty if buy_qty > 0 else Decimal(0)
        result[symbol_id] = {"quantity": quantity, "avg_entry_price": avg_entry}
    return result


def get_derived_cash(session: Session, portfolio: PaperPortfolio) -> Decimal:
    cash = portfolio.starting_cash_usd
    for order in _get_filled_orders(session, portfolio.id):
        if order.filled_quantity <= 0 or order.filled_avg_price is None:
            continue
        proceeds = order.filled_quantity * order.filled_avg_price
        cash += proceeds if order.side == PaperOrderSide.SELL else -proceeds
    return cash


def _latest_close(session: Session, symbol_id: int) -> Decimal | None:
    today = date.today()
    bars = get_latest_price_bars(
        session, symbol_id, today - timedelta(days=PRICE_LOOKBACK_DAYS), today
    )
    return bars[-1].close if bars else None


def get_portfolio_snapshot(session: Session, portfolio: PaperPortfolio) -> PortfolioSnapshotOut:
    """The one shared helper every portfolio-facing view reads through
    (mirrors Phase 2's get_latest_price_bars as the single source of truth
    for point-in-time derivation)."""
    cash = get_derived_cash(session, portfolio)
    positions_by_symbol = get_derived_positions(session, portfolio.id)

    position_outs: list[PositionOut] = []
    total_market_value = Decimal(0)
    if positions_by_symbol:
        symbols = {
            s.id: s
            for s in session.execute(
                select(Symbol).where(Symbol.id.in_(positions_by_symbol.keys()))
            ).scalars()
        }
        for symbol_id, pos in positions_by_symbol.items():
            quantity = int(pos["quantity"])
            avg_entry_price = Decimal(pos["avg_entry_price"])
            current_price = _latest_close(session, symbol_id)
            market_value = current_price * quantity if current_price is not None else None
            unrealized_pl = (
                market_value - avg_entry_price * quantity if market_value is not None else None
            )
            if market_value is not None:
                total_market_value += market_value
            position_outs.append(
                PositionOut(
                    ticker=symbols[symbol_id].ticker,
                    quantity=quantity,
                    avg_entry_price=avg_entry_price,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pl=unrealized_pl,
                )
            )

    return PortfolioSnapshotOut(
        cash_usd=cash,
        positions=position_outs,
        total_market_value=total_market_value,
        total_equity=cash + total_market_value,
    )


def validate_order_capital(
    session: Session,
    portfolio: PaperPortfolio,
    symbol_id: int,
    side: PaperOrderSide,
    quantity: int,
    order_type: PaperOrderType,
    limit_price: Decimal | None,
) -> None:
    """Principle 1: preserve capital before pursuing returns. Raises
    InsufficientCapitalError / InsufficientPositionError rather than
    silently clamping the order — the propose endpoint surfaces these as a
    4xx with a plain-English reason."""
    if side == PaperOrderSide.SELL:
        held = int(
            get_derived_positions(session, portfolio.id).get(symbol_id, {}).get("quantity", 0)
        )
        if quantity > held:
            raise InsufficientPositionError(
                f"Cannot sell {quantity} shares — only {held} held (no short selling in this MVP)."
            )
        return

    estimate_price: Decimal | None
    if order_type == PaperOrderType.LIMIT and limit_price is not None:
        estimate_price = limit_price
    else:
        estimate_price = _latest_close(session, symbol_id)
    if estimate_price is None:
        raise ValueError("No recent price data available to estimate order cost.")

    estimated_cost = estimate_price * quantity
    cash = get_derived_cash(session, portfolio)
    if estimated_cost > cash:
        raise InsufficientCapitalError(
            f"Estimated cost {estimated_cost} exceeds available cash {cash} "
            "(principle 1: preserve capital)."
        )
