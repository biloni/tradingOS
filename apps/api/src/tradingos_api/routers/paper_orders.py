from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_broker_provider
from tradingos_api.db.session import get_db
from tradingos_api.models.paper_order import PaperOrder, PaperOrderStatus
from tradingos_api.models.symbol import Symbol
from tradingos_api.providers.broker import PaperBrokerProvider, PaperOrderRequest, PaperOrderResult
from tradingos_api.schemas.paper_order import PaperOrderCreate, PaperOrderOut
from tradingos_api.services.audit import record_audit_event
from tradingos_api.services.paper_orders import map_alpaca_status
from tradingos_api.services.portfolio import (
    InsufficientCapitalError,
    InsufficientPositionError,
    get_or_create_default_portfolio,
    validate_order_capital,
)

router = APIRouter(prefix="/api/v1/paper-orders", tags=["paper-orders"])


def _get_symbol_or_404(session: Session, ticker: str) -> Symbol:
    symbol = session.execute(
        select(Symbol).where(Symbol.ticker == ticker.upper())
    ).scalar_one_or_none()
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    return symbol


def _get_order_or_404(session: Session, order_id: int) -> PaperOrder:
    order = session.get(PaperOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Unknown paper order: {order_id}")
    return order


def _apply_result(order: PaperOrder, result: PaperOrderResult) -> None:
    order.broker_order_id = result.broker_order_id
    order.status = map_alpaca_status(result.status)
    order.filled_quantity = int(result.filled_quantity)
    order.filled_avg_price = Decimal(result.filled_avg_price) if result.filled_avg_price else None
    order.filled_at = datetime.fromisoformat(result.filled_at) if result.filled_at else None


def _to_out(session: Session, order: PaperOrder) -> PaperOrderOut:
    symbol = session.get(Symbol, order.symbol_id)
    assert symbol is not None
    return PaperOrderOut(
        id=order.id,
        portfolio_id=order.portfolio_id,
        ticker=symbol.ticker,
        side=order.side,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        order_type=order.order_type,
        limit_price=order.limit_price,
        status=order.status,
        broker_order_id=order.broker_order_id,
        filled_avg_price=order.filled_avg_price,
        filled_at=order.filled_at,
        submitted_at=order.submitted_at,
        created_at=order.created_at,
    )


@router.post("", response_model=PaperOrderOut, status_code=201)
def propose_paper_order(
    body: PaperOrderCreate, session: Annotated[Session, Depends(get_db)]
) -> PaperOrderOut:
    """Step 1 of 2 (principle 11): validates and records a DRAFT order.
    Nothing is sent to Alpaca yet — see `confirm_paper_order` below."""
    symbol = _get_symbol_or_404(session, body.ticker)
    portfolio = get_or_create_default_portfolio(session)

    try:
        validate_order_capital(
            session,
            portfolio,
            symbol.id,
            body.side,
            body.quantity,
            body.order_type,
            body.limit_price,
        )
    except (InsufficientCapitalError, InsufficientPositionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    order = PaperOrder(
        portfolio_id=portfolio.id,
        symbol_id=symbol.id,
        side=body.side,
        quantity=body.quantity,
        order_type=body.order_type,
        limit_price=body.limit_price,
        status=PaperOrderStatus.DRAFT,
        filled_quantity=0,
        created_at=datetime.now(UTC),
    )
    session.add(order)
    session.flush()
    record_audit_event(
        session,
        record_type="PAPER_ORDER_PROPOSED",
        ref_id=order.id,
        snapshot={
            "ticker": symbol.ticker,
            "side": body.side.value,
            "quantity": body.quantity,
            "order_type": body.order_type.value,
            "limit_price": str(body.limit_price) if body.limit_price else None,
        },
    )
    session.commit()
    return _to_out(session, order)


@router.post("/{order_id}/confirm", response_model=PaperOrderOut)
def confirm_paper_order(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    broker: Annotated[PaperBrokerProvider, Depends(get_broker_provider)],
) -> PaperOrderOut:
    """Step 2 of 2 (principle 11): the explicit human-confirmation action
    that actually submits the order to Alpaca's paper-trading API. Only a
    DRAFT order can be confirmed — this is not a re-triable "retry" button;
    a stuck/failed confirm should be investigated, not silently repeated."""
    order = _get_order_or_404(session, order_id)
    if order.status != PaperOrderStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only DRAFT orders can be confirmed (this order is {order.status.value}).",
        )

    symbol = session.get(Symbol, order.symbol_id)
    assert symbol is not None
    portfolio = get_or_create_default_portfolio(session)

    # Re-validate immediately before submission — prices/positions may have
    # moved since the order was proposed (principle 1).
    try:
        validate_order_capital(
            session,
            portfolio,
            symbol.id,
            order.side,
            order.quantity,
            order.order_type,
            order.limit_price,
        )
    except (InsufficientCapitalError, InsufficientPositionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request = PaperOrderRequest(
        symbol=symbol.ticker,
        quantity=order.quantity,
        side=order.side.value.lower(),
        order_type=order.order_type.value.lower(),
        limit_price=str(order.limit_price) if order.limit_price is not None else None,
    )
    result = broker.submit_paper_order(request)
    if map_alpaca_status(result.status) == PaperOrderStatus.SUBMITTED:
        # Fills are asynchronous — a market order's submit response commonly
        # reflects a pre-fill state ("new"/"accepted"). One immediate
        # re-check catches a same-cycle fill (the common case during market
        # hours); anything slower is caught by the /refresh endpoint below.
        result = broker.get_paper_order_status(result.broker_order_id)

    _apply_result(order, result)
    order.submitted_at = datetime.now(UTC)

    record_audit_event(
        session,
        record_type="PAPER_ORDER_CONFIRMED",
        ref_id=order.id,
        snapshot={
            "broker_order_id": order.broker_order_id,
            "broker_raw_status": result.status,
            "mapped_status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
        },
    )
    session.commit()
    return _to_out(session, order)


@router.post("/{order_id}/refresh", response_model=PaperOrderOut)
def refresh_paper_order(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    broker: Annotated[PaperBrokerProvider, Depends(get_broker_provider)],
) -> PaperOrderOut:
    """Re-syncs status/fill fields from the broker for an order that hasn't
    reached a terminal state yet. Needed because fills are asynchronous —
    see `PaperBrokerProvider.get_paper_order_status`'s docstring. A future
    UI would poll this for any order still SUBMITTED/PARTIALLY_FILLED."""
    order = _get_order_or_404(session, order_id)
    if order.status not in (PaperOrderStatus.SUBMITTED, PaperOrderStatus.PARTIALLY_FILLED):
        raise HTTPException(
            status_code=400,
            detail=f"Order is {order.status.value}; nothing to refresh.",
        )
    if not order.broker_order_id:
        raise HTTPException(status_code=400, detail="Order has no broker_order_id to refresh from.")

    result = broker.get_paper_order_status(order.broker_order_id)
    previous_status = order.status
    _apply_result(order, result)

    record_audit_event(
        session,
        record_type="PAPER_ORDER_REFRESHED",
        ref_id=order.id,
        snapshot={
            "previous_status": previous_status.value,
            "broker_raw_status": result.status,
            "mapped_status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
        },
    )
    session.commit()
    return _to_out(session, order)


@router.post("/{order_id}/cancel", response_model=PaperOrderOut)
def cancel_paper_order(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    broker: Annotated[PaperBrokerProvider, Depends(get_broker_provider)],
) -> PaperOrderOut:
    order = _get_order_or_404(session, order_id)
    if order.status not in (PaperOrderStatus.DRAFT, PaperOrderStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel an order in status {order.status.value}.",
        )

    if order.status == PaperOrderStatus.SUBMITTED and order.broker_order_id:
        broker.cancel_paper_order(order.broker_order_id)

    order.status = PaperOrderStatus.CANCELED
    record_audit_event(session, record_type="PAPER_ORDER_CANCELED", ref_id=order.id, snapshot={})
    session.commit()
    return _to_out(session, order)


@router.get("", response_model=list[PaperOrderOut])
def list_paper_orders(session: Annotated[Session, Depends(get_db)]) -> list[PaperOrderOut]:
    orders = (
        session.execute(select(PaperOrder).order_by(PaperOrder.created_at.desc())).scalars().all()
    )
    return [_to_out(session, order) for order in orders]


@router.get("/{order_id}", response_model=PaperOrderOut)
def get_paper_order(order_id: int, session: Annotated[Session, Depends(get_db)]) -> PaperOrderOut:
    order = _get_order_or_404(session, order_id)
    return _to_out(session, order)
