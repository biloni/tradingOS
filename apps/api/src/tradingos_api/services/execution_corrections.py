"""Corrections through reversal (Revision Prompt 8): "never silently
delete or rewrite an executed event." A correction is always a brand
new, real `Execution` row — the original row is never touched, updated,
or removed.

**Reversing a buy is exact.** The specific lot that buy created
(`PositionLot.opened_execution_id == original_execution.id`) is found
directly and closed out — not routed through general FIFO consumption,
which could otherwise (if an older lot exists in the same lane) close
the wrong lot instead of the one actually being corrected.

**Reversing a sell is an economic approximation, documented as such.**
`services/portfolio_accounting.py`'s `ApplyExecutionResult.consumed_lots`
is a return value, not a persisted record of exactly which lots (and
how much of each) a given sell drew from — recovering that later would
require a new per-consumption ledger table this revision does not add.
`reverse_sell_execution()` instead opens a new lot (same lane, same
quantity/price as the original sell) — economically equivalent (the
account ends up with the same net position and cash it would have had
if the sell never happened) but not a lot-for-lot undo of the original
FIFO consumption. This is a known, explicit limitation, not a silent
approximation."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import CashLedgerEntryType, LotLane, OrderSide
from tradingos_api.models.execution import CashLedgerEntry, Execution, PositionLot
from tradingos_api.models.portfolio_ext import ExecutionCorrection
from tradingos_api.services.portfolio_accounting import (
    apply_buy_execution,
    recompute_position_aggregate,
)

CALCULATION_VERSION = "v1"


def reverse_buy_execution(
    db: Session,
    *,
    original_execution: Execution,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    reason: str,
    corrected_at: datetime,
) -> ExecutionCorrection:
    lot = db.scalar(
        select(PositionLot).where(PositionLot.opened_execution_id == original_execution.id)
    )
    if lot is None:
        raise ValueError("no lot found for the original buy execution — nothing to reverse")
    if lot.quantity_remaining == 0:
        raise ValueError(
            "this lot has already been fully sold — there is no remaining open "
            "quantity left to reverse"
        )

    reversal = Execution(
        order_id=original_execution.order_id,
        quantity=lot.quantity_remaining,
        price=original_execution.price,
        executed_at=corrected_at,
    )
    db.add(reversal)
    db.flush()

    lot.quantity_remaining = Decimal(0)
    lot.closed_at = corrected_at

    db.add(
        CashLedgerEntry(
            account_id=account_id,
            entry_type=CashLedgerEntryType.TRADE_CREDIT,
            amount=reversal.quantity * reversal.price,
            related_execution_id=reversal.id,
            occurred_at=corrected_at,
        )
    )
    recompute_position_aggregate(db, account_id=account_id, instrument_id=instrument_id)

    correction = ExecutionCorrection(
        original_execution_id=original_execution.id,
        reversal_execution_id=reversal.id,
        reason=reason,
        corrected_at=corrected_at,
    )
    db.add(correction)
    db.flush()
    return correction


def reverse_sell_execution(
    db: Session,
    *,
    original_execution: Execution,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    lane: LotLane,
    reason: str,
    corrected_at: datetime,
) -> ExecutionCorrection:
    """See module docstring — an economic approximation, not a
    lot-for-lot undo of the original sell's FIFO consumption."""
    reversal = Execution(
        order_id=original_execution.order_id,
        quantity=original_execution.quantity,
        price=original_execution.price,
        executed_at=corrected_at,
    )
    db.add(reversal)
    db.flush()

    apply_buy_execution(
        db,
        execution=reversal,
        account_id=account_id,
        instrument_id=instrument_id,
        lane=lane,
    )

    correction = ExecutionCorrection(
        original_execution_id=original_execution.id,
        reversal_execution_id=reversal.id,
        reason=(
            f"{reason} (economic approximation — reopens a new lot rather than "
            "restoring the exact original FIFO consumption; see reverse_sell_execution "
            "docstring)"
        ),
        corrected_at=corrected_at,
    )
    db.add(correction)
    db.flush()
    return correction


def reverse_execution(
    db: Session,
    *,
    original_execution: Execution,
    original_side: OrderSide,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    lane: LotLane,
    reason: str,
    corrected_at: datetime,
) -> ExecutionCorrection:
    if original_side == OrderSide.BUY:
        return reverse_buy_execution(
            db,
            original_execution=original_execution,
            account_id=account_id,
            instrument_id=instrument_id,
            reason=reason,
            corrected_at=corrected_at,
        )
    return reverse_sell_execution(
        db,
        original_execution=original_execution,
        account_id=account_id,
        instrument_id=instrument_id,
        lane=lane,
        reason=reason,
        corrected_at=corrected_at,
    )
