"""Manual trade entry, order import, fills, and reconciliation
(docs/API_CONTRACTS.md area 6).

`confirm` is the principle-11 human-confirmation gate (ADR-014, unchanged
from the shipped MVP): `POST /orders` only ever creates a `DRAFT` row;
`POST /orders/{id}/confirm` is the one action that actually posts a fill.
No live broker call happens for either account type this pass ("do not
integrate external providers yet") — a `MANUAL` account's confirm fills
immediately at the given/implied price (there's no broker to wait on); a
`PAPER_ALPACA` account's confirm marks the order `SUBMITTED` without a
real Alpaca call, clearly distinct from a real fill.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_broker_provider, require_step_up
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import (
    ORDER_TRANSITIONS,
    AccountType,
    CashLedgerEntryType,
    OrderLegRole,
    OrderStatus,
)
from tradingos_api.models.execution import (
    Account,
    CashLedgerEntry,
    Execution,
    Order,
    OrderLeg,
    Position,
    PositionLot,
)
from tradingos_api.models.order_authority import CancelOpenOrdersEvent
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.order_authority import CancelOpenOrdersRequest, CancelOpenOrdersResponse
from tradingos_api.schemas.orders import (
    ExecutionResponse,
    OrderCreateRequest,
    OrderImportRequest,
    OrderResponse,
    ReconciliationRow,
)
from tradingos_api.services.lifecycle import InvalidTransitionError, assert_transition_allowed
from tradingos_api.services.order_execution import cancel_order_at_broker

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _order_response(db: Session, order: Order) -> OrderResponse:
    inst = db.get(Instrument, order.instrument_id)
    assert inst is not None
    execs = db.scalars(select(Execution).where(Execution.order_id == order.id)).all()
    return OrderResponse(
        id=order.id,
        account_id=order.account_id,
        instrument=InstrumentResponse.model_validate(inst),
        side=order.side,
        order_type=order.order_type,
        time_in_force=order.time_in_force,
        quantity=order.quantity,
        limit_price=order.limit_price,
        status=order.status,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        created_at=order.created_at,
        executions=[ExecutionResponse.model_validate(e) for e in execs],
    )


def _apply_fill(
    db: Session,
    account: Account,
    order: Order,
    quantity: Decimal,
    price: Decimal,
    executed_at: datetime,
) -> Execution:
    """Books an execution: writes the fact, updates the derived position +
    opens/consumes lots, and posts the corresponding cash-ledger entry —
    the three things that must always move together. A BUY opens a new
    FIFO lot; a SELL consumes existing open lots oldest-first, which is
    what keeps `position.quantity` and `sum(position_lots.quantity_remaining)`
    from diverging (the invariant `tests/test_invariants.py` checks).
    Selling more than currently held (short selling) is out of scope for
    this long-only journal — `position.quantity` can go negative but lot
    consumption simply stops once open lots are exhausted."""
    execution = Execution(
        order_id=order.id, quantity=quantity, price=price, executed_at=executed_at
    )
    db.add(execution)
    db.flush()

    signed_qty = quantity if order.side == "BUY" else -quantity
    position = db.scalar(
        select(Position).where(
            Position.account_id == account.id, Position.instrument_id == order.instrument_id
        )
    )
    if position is None:
        position = Position(
            account_id=account.id,
            instrument_id=order.instrument_id,
            quantity=Decimal(0),
            avg_cost=Decimal(0),
            opened_at=executed_at,
        )
        db.add(position)
        db.flush()

    new_quantity = position.quantity + signed_qty
    if order.side == "BUY" and position.quantity >= 0:
        total_cost = position.avg_cost * position.quantity + price * quantity
        position.avg_cost = (total_cost / new_quantity) if new_quantity != 0 else Decimal(0)
        db.add(
            PositionLot(
                position_id=position.id,
                account_id=account.id,
                instrument_id=order.instrument_id,
                opened_execution_id=execution.id,
                quantity_opened=quantity,
                quantity_remaining=quantity,
                cost_basis_price=price,
                opened_at=executed_at,
            )
        )
    elif order.side == "SELL":
        remaining_to_consume = quantity
        open_lots = db.scalars(
            select(PositionLot)
            .where(
                PositionLot.account_id == account.id,
                PositionLot.instrument_id == order.instrument_id,
                PositionLot.quantity_remaining > 0,
            )
            .order_by(PositionLot.opened_at.asc())
        ).all()
        for lot in open_lots:
            if remaining_to_consume <= 0:
                break
            consumed = min(lot.quantity_remaining, remaining_to_consume)
            lot.quantity_remaining -= consumed
            remaining_to_consume -= consumed
            if lot.quantity_remaining == 0:
                lot.closed_at = executed_at
    position.quantity = new_quantity

    cash_delta = -(price * quantity) if order.side == "BUY" else (price * quantity)
    entry_type = (
        CashLedgerEntryType.TRADE_DEBIT if cash_delta < 0 else CashLedgerEntryType.TRADE_CREDIT
    )
    db.add(
        CashLedgerEntry(
            account_id=account.id,
            entry_type=entry_type,
            amount=cash_delta,
            related_order_id=order.id,
            related_execution_id=execution.id,
            occurred_at=executed_at,
            idempotency_key=f"exec-{execution.id}",
        )
    )
    return execution


@router.get("", response_model=Page[OrderResponse])
def list_orders(
    db: Session = Depends(get_db),
    account_id: uuid.UUID | None = Query(default=None),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[OrderResponse]:
    stmt = select(Order).order_by(Order.created_at.desc())
    if account_id is not None:
        stmt = stmt.where(Order.account_id == account_id)
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    items = [_order_response(db, o) for o in page_rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> OrderResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    return _order_response(db, order)


@router.post("", response_model=OrderResponse, status_code=201)
def propose_order(payload: OrderCreateRequest, db: Session = Depends(get_db)) -> OrderResponse:
    account = db.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(status_code=422, detail="Unknown account_id.")
    if db.get(Instrument, payload.instrument_id) is None:
        raise HTTPException(status_code=422, detail="Unknown instrument_id.")

    if payload.idempotency_key:
        existing = db.scalar(select(Order).where(Order.idempotency_key == payload.idempotency_key))
        if existing is not None:
            return _order_response(db, existing)

    order = Order(
        account_id=payload.account_id,
        instrument_id=payload.instrument_id,
        side=payload.side,
        order_type=payload.order_type,
        time_in_force=payload.time_in_force,
        quantity=payload.quantity,
        limit_price=payload.limit_price,
        status=OrderStatus.DRAFT,
        idempotency_key=payload.idempotency_key,
    )
    db.add(order)
    db.flush()
    db.add(OrderLeg(order_id=order.id, role=OrderLegRole.PRIMARY))
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> OrderResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    account = db.get(Account, order.account_id)
    assert account is not None

    is_manual = account.account_type == AccountType.MANUAL
    target_status = OrderStatus.FILLED if is_manual else OrderStatus.SUBMITTED
    try:
        assert_transition_allowed("Order", order.status, target_status, ORDER_TRANSITIONS)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(UTC)
    order.submitted_at = now
    if target_status == OrderStatus.FILLED:
        price = order.limit_price or Decimal("0")
        if price == 0:
            raise HTTPException(
                status_code=422,
                detail="A manual-account fill needs a limit_price to record the fill price.",
            )
        _apply_fill(db, account, order, order.quantity, price, now)
        order.filled_at = now
    order.status = target_status
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> OrderResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    try:
        assert_transition_allowed("Order", order.status, OrderStatus.CANCELED, ORDER_TRANSITIONS)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    order.status = OrderStatus.CANCELED
    order.canceled_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@router.post("/import", response_model=list[OrderResponse], status_code=201)
def import_fills(payload: OrderImportRequest, db: Session = Depends(get_db)) -> list[OrderResponse]:
    """Backfills already-filled historical trades in bulk — each row
    becomes a FILLED order + execution directly, skipping the propose/
    confirm gate (there's nothing to confirm about something that already
    happened at the user's real broker)."""
    account = db.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(status_code=422, detail="Unknown account_id.")

    created: list[Order] = []
    for row in payload.fills:
        if row.idempotency_key:
            existing = db.scalar(select(Order).where(Order.idempotency_key == row.idempotency_key))
            if existing is not None:
                created.append(existing)
                continue
        if db.get(Instrument, row.instrument_id) is None:
            raise HTTPException(
                status_code=422, detail=f"Unknown instrument_id {row.instrument_id}."
            )

        order = Order(
            account_id=account.id,
            instrument_id=row.instrument_id,
            side=row.side,
            order_type="MARKET",
            quantity=row.quantity,
            status=OrderStatus.FILLED,
            submitted_at=row.executed_at,
            filled_at=row.executed_at,
            idempotency_key=row.idempotency_key,
        )
        db.add(order)
        db.flush()
        db.add(OrderLeg(order_id=order.id, role=OrderLegRole.PRIMARY))
        _apply_fill(db, account, order, row.quantity, row.price, row.executed_at)
        created.append(order)

    db.commit()
    return [_order_response(db, o) for o in created]


@router.get("/reconciliation/{account_id}", response_model=list[ReconciliationRow])
def get_reconciliation(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[ReconciliationRow]:
    """Self-consistency check: the `Position` aggregate vs. the sum of its
    own `PositionLot` rows. There is no live broker to reconcile against
    this pass — this is the internal-consistency analogue of the shipped
    MVP's Alpaca-vs-derived reconciliation, checking that the two places
    this app itself tracks quantity never silently diverge."""
    if db.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    positions = db.scalars(select(Position).where(Position.account_id == account_id)).all()
    rows: list[ReconciliationRow] = []
    for pos in positions:
        inst = db.get(Instrument, pos.instrument_id)
        assert inst is not None
        lots_total = db.scalar(
            select(func.coalesce(func.sum(PositionLot.quantity_remaining), 0)).where(
                PositionLot.position_id == pos.id
            )
        ) or Decimal(0)
        rows.append(
            ReconciliationRow(
                account_id=account_id,
                instrument_id=pos.instrument_id,
                ticker=inst.ticker,
                position_quantity=pos.quantity,
                lots_quantity=lots_total,
                discrepancy=pos.quantity - lots_total,
            )
        )
    return rows


@router.post("/cancel-open", response_model=CancelOpenOrdersResponse)
def cancel_open_orders(
    payload: CancelOpenOrdersRequest,
    db: Session = Depends(get_db),
    broker: PaperBrokerProvider = Depends(get_broker_provider),
    _step_up: None = Depends(require_step_up),
) -> CancelOpenOrdersResponse:
    """OA-9/SS-4's second, independent control — "a separate action that
    cancels every open order still at the broker, independent of the
    kill switch." Requires step-up (Revision Prompt 16): cancel-all can
    remove protective stop/target legs, not just entries, so it can
    increase realized risk even though it reads as "just cancelling."
    Scoped to `payload.account_id` (or every `PAPER_ALPACA`
    account if omitted) and only orders that actually reached a broker
    (`broker_order_id IS NOT NULL`) — a `MANUAL` account's orders have no
    broker leg to cancel there. Every cancellation still goes through
    `services/order_execution.py::cancel_order_at_broker()`, the only
    other function besides the submit path that touches
    `PaperBrokerProvider`."""
    stmt = select(Order).where(
        Order.status.in_((OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)),
        Order.broker_order_id.is_not(None),
    )
    if payload.account_id is not None:
        stmt = stmt.where(Order.account_id == payload.account_id)
    else:
        paper_account_ids = db.scalars(
            select(Account.id).where(Account.account_type == AccountType.PAPER_ALPACA)
        ).all()
        stmt = stmt.where(Order.account_id.in_(paper_account_ids))

    open_orders = db.scalars(stmt).all()
    canceled_ids: list[uuid.UUID] = []
    for order in open_orders:
        cancel_order_at_broker(db, order=order, broker=broker)
        canceled_ids.append(order.id)

    db.add(
        CancelOpenOrdersEvent(
            account_id=payload.account_id,
            triggered_by=payload.triggered_by,
            triggered_at=datetime.now(UTC),
            reason=payload.reason,
            orders_canceled_count=len(canceled_ids),
        )
    )
    db.commit()
    return CancelOpenOrdersResponse(
        orders_canceled_count=len(canceled_ids), canceled_order_ids=canceled_ids
    )
