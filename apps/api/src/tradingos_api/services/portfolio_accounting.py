"""The core portfolio accounting engine (Revision Prompt 8): holdings,
cash, lots, realized P&L, and fees are always *derived* from the
append-only `Execution`/`Fee`/`CashLedgerEntry` facts — never stored as
an independently-mutable primary value (the same "current state is a
derived view" philosophy `services/snapshot.py`-equivalent logic uses
everywhere else in this project). Every monetary/quantity computation
here uses `decimal.Decimal` — never a native float.

**Lane-aware FIFO, not lane-blind FIFO.** A broker only ever reports one
combined position per (account, instrument) — it has no concept of
"this lot is the Investment thesis, that lot is the earnings trade."
This engine tracks that distinction internally: `apply_sell_execution()`
takes an explicit `target_lane` naming which lane's shares this sell is
closing, and consumes *only* that lane's open lots in FIFO (open-date)
order. This is what "prevent an exit intended for the tactical lot from
being represented as closing the investment thesis unless lot/order
behavior actually does so" means in code — a sell can never accidentally
eat into a different lane's lots just because they happen to be older.

**Documented broker limitation (lot-selection uncertainty):** a real
broker fill event usually does not tell you *which* lots it closed, only
a net quantity and price. `target_lane=None` models that case honestly —
FIFO runs across every lane's open lots as one combined pool, and the
resulting lot consumption is disclosed as `lane_selection_is_certain=False`
on the result, so a caller (and the UI) can show "this exit's lane
attribution is the system's best FIFO inference, not a broker-confirmed
fact" rather than presenting an inferred split as certain.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import CashLedgerEntryType, LotLane, OrderSide, TradeStatus
from tradingos_api.models.execution import (
    CashLedgerEntry,
    Execution,
    Fee,
    Position,
    PositionLot,
    Trade,
)

CALCULATION_VERSION = "v1"


class InsufficientLotsError(Exception):
    """Raised when a sell targets a lane (or the combined position) that
    does not have enough open quantity to cover it — fails closed rather
    than silently going negative or borrowing from a different lane."""


@dataclass(frozen=True)
class LotConsumption:
    lot_id: uuid.UUID
    quantity_consumed: Decimal
    cost_basis_price: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class ApplyExecutionResult:
    position_id: uuid.UUID
    cash_ledger_entry_id: uuid.UUID
    created_lot_id: uuid.UUID | None = None
    consumed_lots: list[LotConsumption] = field(default_factory=list)
    realized_pnl: Decimal = Decimal(0)
    trade_id: uuid.UUID | None = None
    trade_opened: bool = False
    trade_closed: bool = False
    lane_selection_is_certain: bool = True


@dataclass(frozen=True)
class SubpositionSummary:
    lane: LotLane
    quantity: Decimal
    avg_cost: Decimal
    lot_count: int


def get_or_create_position(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> Position:
    position = db.scalar(
        select(Position).where(
            Position.account_id == account_id, Position.instrument_id == instrument_id
        )
    )
    if position is None:
        position = Position(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=Decimal(0),
            avg_cost=Decimal(0),
        )
        db.add(position)
        db.flush()
    return position


def get_open_lots(
    db: Session,
    *,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    lane: LotLane | None = None,
) -> list[PositionLot]:
    """Oldest-opened-first (FIFO order). `lane=None` returns every open
    lot across all lanes, in true open-date order regardless of lane —
    this is the "broker cannot guarantee tax-lot selection" pool."""
    stmt = (
        select(PositionLot)
        .where(
            PositionLot.account_id == account_id,
            PositionLot.instrument_id == instrument_id,
            PositionLot.quantity_remaining > 0,
        )
        .order_by(PositionLot.opened_at.asc())
    )
    if lane is not None:
        stmt = stmt.where(PositionLot.lane == lane)
    return list(db.scalars(stmt).all())


def _lane_aggregate_quantity(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID, lane: LotLane
) -> Decimal:
    return sum(
        (
            lot.quantity_remaining
            for lot in get_open_lots(
                db, account_id=account_id, instrument_id=instrument_id, lane=lane
            )
        ),
        Decimal(0),
    )


def get_subpositions_by_lane(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> dict[LotLane, SubpositionSummary]:
    """ "Separate analytical subpositions" — one summary per lane that
    currently has any open quantity. A lane absent from the returned
    dict has no open position in it (never a zero-valued placeholder
    row a caller has to filter out)."""
    summaries: dict[LotLane, SubpositionSummary] = {}
    for lane in LotLane:
        lots = get_open_lots(db, account_id=account_id, instrument_id=instrument_id, lane=lane)
        if not lots:
            continue
        total_qty = sum((lot.quantity_remaining for lot in lots), Decimal(0))
        total_cost = sum(
            (lot.quantity_remaining * lot.cost_basis_price for lot in lots), Decimal(0)
        )
        avg_cost = (total_cost / total_qty) if total_qty != 0 else Decimal(0)
        summaries[lane] = SubpositionSummary(
            lane=lane, quantity=total_qty, avg_cost=avg_cost, lot_count=len(lots)
        )
    return summaries


def recompute_position_aggregate(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> Position:
    """The combined broker position — lane-blind by construction, summed
    across every lane's open lots, since a real broker has no concept of
    lanes at all. This is the one function that turns `PositionLot` rows
    back into the single `Position.quantity`/`avg_cost` a broker
    statement would show."""
    position = get_or_create_position(db, account_id=account_id, instrument_id=instrument_id)
    lots = get_open_lots(db, account_id=account_id, instrument_id=instrument_id)
    total_qty = sum((lot.quantity_remaining for lot in lots), Decimal(0))
    total_cost = sum((lot.quantity_remaining * lot.cost_basis_price for lot in lots), Decimal(0))
    position.quantity = total_qty
    position.avg_cost = (total_cost / total_qty) if total_qty != 0 else Decimal(0)
    db.flush()
    return position


def _find_open_trade(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID, lane: LotLane
) -> Trade | None:
    return db.scalar(
        select(Trade).where(
            Trade.account_id == account_id,
            Trade.instrument_id == instrument_id,
            Trade.lane == lane,
            Trade.status == TradeStatus.OPEN,
        )
    )


def apply_buy_execution(
    db: Session,
    *,
    execution: Execution,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    lane: LotLane,
    source_recommendation_version_id: uuid.UUID | None = None,
) -> ApplyExecutionResult:
    """A buy always opens a new lot — lots are never merged, even for
    repeated buys in the same lane on the same day (each fill is its own
    immutable cost-basis fact, matching "never silently delete or
    rewrite an executed event" applied to lot creation too)."""
    position = get_or_create_position(db, account_id=account_id, instrument_id=instrument_id)

    lane_qty_before = _lane_aggregate_quantity(
        db, account_id=account_id, instrument_id=instrument_id, lane=lane
    )

    lot = PositionLot(
        position_id=position.id,
        account_id=account_id,
        instrument_id=instrument_id,
        opened_execution_id=execution.id,
        quantity_opened=execution.quantity,
        quantity_remaining=execution.quantity,
        cost_basis_price=execution.price,
        opened_at=execution.executed_at,
        lane=lane,
        source_recommendation_version_id=source_recommendation_version_id,
    )
    db.add(lot)
    db.flush()

    cash_entry = CashLedgerEntry(
        account_id=account_id,
        entry_type=CashLedgerEntryType.TRADE_DEBIT,
        amount=-(execution.quantity * execution.price),
        related_execution_id=execution.id,
        occurred_at=execution.executed_at,
    )
    db.add(cash_entry)
    db.flush()

    recompute_position_aggregate(db, account_id=account_id, instrument_id=instrument_id)

    trade_id: uuid.UUID | None = None
    trade_opened = False
    if lane_qty_before == 0:
        trade = Trade(
            account_id=account_id,
            instrument_id=instrument_id,
            status=TradeStatus.OPEN,
            opened_at=execution.executed_at,
            quantity=execution.quantity,
            lane=lane,
            linked_order_id=execution.order_id,
        )
        db.add(trade)
        db.flush()
        trade_id = trade.id
        trade_opened = True
    else:
        existing = _find_open_trade(
            db, account_id=account_id, instrument_id=instrument_id, lane=lane
        )
        if existing is not None:
            existing.quantity += execution.quantity
            trade_id = existing.id

    return ApplyExecutionResult(
        position_id=position.id,
        cash_ledger_entry_id=cash_entry.id,
        created_lot_id=lot.id,
        trade_id=trade_id,
        trade_opened=trade_opened,
    )


def apply_sell_execution(
    db: Session,
    *,
    execution: Execution,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    target_lane: LotLane | None,
) -> ApplyExecutionResult:
    """Consumes open lots in FIFO (open-date) order, restricted to
    `target_lane` when given. Raises `InsufficientLotsError` if the
    targeted pool does not have enough open quantity — never partially
    fills past what actually exists, and never silently reaches into a
    different lane's lots to make up the shortfall."""
    position = get_or_create_position(db, account_id=account_id, instrument_id=instrument_id)
    lots = get_open_lots(db, account_id=account_id, instrument_id=instrument_id, lane=target_lane)

    available = sum((lot.quantity_remaining for lot in lots), Decimal(0))
    if available < execution.quantity:
        pool = f"lane {target_lane.value}" if target_lane is not None else "the combined position"
        raise InsufficientLotsError(
            f"sell of {execution.quantity} exceeds {available} open in {pool} "
            f"for instrument {instrument_id}"
        )

    remaining_to_consume = execution.quantity
    consumed: list[LotConsumption] = []
    total_realized_pnl = Decimal(0)
    realized_pnl_by_lane: dict[LotLane, Decimal] = {}

    for lot in lots:
        if remaining_to_consume <= 0:
            break
        take = min(lot.quantity_remaining, remaining_to_consume)
        lot.quantity_remaining -= take
        if lot.quantity_remaining == 0:
            lot.closed_at = execution.executed_at
        realized = (execution.price - lot.cost_basis_price) * take
        total_realized_pnl += realized
        realized_pnl_by_lane[lot.lane] = realized_pnl_by_lane.get(lot.lane, Decimal(0)) + realized
        consumed.append(
            LotConsumption(
                lot_id=lot.id,
                quantity_consumed=take,
                cost_basis_price=lot.cost_basis_price,
                realized_pnl=realized,
            )
        )
        remaining_to_consume -= take

    db.flush()

    cash_entry = CashLedgerEntry(
        account_id=account_id,
        entry_type=CashLedgerEntryType.TRADE_CREDIT,
        amount=execution.quantity * execution.price,
        related_execution_id=execution.id,
        occurred_at=execution.executed_at,
    )
    db.add(cash_entry)
    db.flush()

    recompute_position_aggregate(db, account_id=account_id, instrument_id=instrument_id)

    trade_id: uuid.UUID | None = None
    trade_closed = False
    for lane, lane_realized_pnl in realized_pnl_by_lane.items():
        trade = _find_open_trade(db, account_id=account_id, instrument_id=instrument_id, lane=lane)
        if trade is None:
            continue
        trade_id = trade.id
        trade.realized_pnl = (trade.realized_pnl or Decimal(0)) + lane_realized_pnl
        lane_qty_after = _lane_aggregate_quantity(
            db, account_id=account_id, instrument_id=instrument_id, lane=lane
        )
        if lane_qty_after == 0:
            trade.status = TradeStatus.CLOSED
            trade.closed_at = execution.executed_at
            trade_closed = True

    return ApplyExecutionResult(
        position_id=position.id,
        cash_ledger_entry_id=cash_entry.id,
        consumed_lots=consumed,
        realized_pnl=total_realized_pnl,
        trade_id=trade_id,
        trade_closed=trade_closed,
        lane_selection_is_certain=target_lane is not None,
    )


def apply_execution(
    db: Session,
    *,
    execution: Execution,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    side: OrderSide,
    lane: LotLane = LotLane.UNCLASSIFIED,
    source_recommendation_version_id: uuid.UUID | None = None,
    target_lane: LotLane | None = None,
) -> ApplyExecutionResult:
    """The one entry point a caller (order-fill recording, CSV import,
    a correction reversal) should use — dispatches to
    `apply_buy_execution`/`apply_sell_execution` by `side`."""
    if side == OrderSide.BUY:
        return apply_buy_execution(
            db,
            execution=execution,
            account_id=account_id,
            instrument_id=instrument_id,
            lane=lane,
            source_recommendation_version_id=source_recommendation_version_id,
        )
    return apply_sell_execution(
        db,
        execution=execution,
        account_id=account_id,
        instrument_id=instrument_id,
        target_lane=target_lane
        if target_lane is not None
        else (lane if lane != LotLane.UNCLASSIFIED else None),
    )


def apply_fee(
    db: Session, *, fee: Fee, account_id: uuid.UUID, occurred_at: datetime
) -> CashLedgerEntry:
    cash_entry = CashLedgerEntry(
        account_id=account_id,
        entry_type=CashLedgerEntryType.FEE,
        amount=-fee.amount,
        related_execution_id=fee.execution_id,
        occurred_at=occurred_at,
    )
    db.add(cash_entry)
    db.flush()
    return cash_entry


def get_cash_balance(db: Session, *, account_id: uuid.UUID, starting_cash: Decimal) -> Decimal:
    ledger_sum = sum(
        (
            entry.amount
            for entry in db.scalars(
                select(CashLedgerEntry).where(CashLedgerEntry.account_id == account_id)
            ).all()
        ),
        Decimal(0),
    )
    return starting_cash + ledger_sum
