"""Broker aggregate position reconciliation (Revision Prompt 8) —
compares the internally-derived combined position (`recompute_position_aggregate()`,
lane-blind, exactly what a broker statement would show) against a
broker-reported quantity per instrument. A `MANUAL` account has no
broker feed at all: every instrument it holds reconciles as `MATCHED`
with `broker_reported_quantity=None` — "nothing to compare against" is
never presented as a discrepancy.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import ReconciliationStatus
from tradingos_api.models.execution import PositionLot
from tradingos_api.models.portfolio_ext import ReconciliationLine, ReconciliationRun
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.services.portfolio_accounting import recompute_position_aggregate

CALCULATION_VERSION = "v1"


def _held_instrument_ids(db: Session, *, account_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.scalars(
        select(PositionLot.instrument_id).where(
            PositionLot.account_id == account_id, PositionLot.quantity_remaining > 0
        )
    ).all()
    return set(rows)


def run_reconciliation(
    db: Session,
    *,
    account_id: uuid.UUID,
    as_of: datetime,
    broker_reported_positions: dict[uuid.UUID, Decimal] | None,
    idempotency_key: str | None = None,
) -> tuple[ReconciliationRun, bool]:
    """`broker_reported_positions=None` or `{}` models a `MANUAL`
    account with no broker feed — every internally-held instrument
    reconciles `MATCHED` with a `None` broker figure. When a dict is
    given, every instrument in *either* the internal holdings or the
    broker report is checked, so a broker-reported position with zero
    internal lots (a real discrepancy — the system doesn't know about a
    position the broker has) is caught too, not just the reverse.

    Returns `(run, replayed)`. When `idempotency_key` is given and a
    run with that key already exists, returns it unchanged
    (`replayed=True`) instead of creating a duplicate run/line set —
    the same "look up by key before insert" pattern this project
    already uses for `Order.idempotency_key` (Revision Prompt 16
    idempotency review)."""
    if idempotency_key is not None:
        existing = db.scalar(
            select(ReconciliationRun).where(ReconciliationRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, True

    broker_reported_positions = broker_reported_positions or {}
    instrument_ids = _held_instrument_ids(db, account_id=account_id) | set(
        broker_reported_positions.keys()
    )

    lines: list[ReconciliationLine] = []
    overall_status = ReconciliationStatus.MATCHED
    for instrument_id in instrument_ids:
        position = recompute_position_aggregate(
            db, account_id=account_id, instrument_id=instrument_id
        )
        broker_quantity = broker_reported_positions.get(instrument_id)

        if broker_quantity is None:
            status = ReconciliationStatus.MATCHED
            detail = None
        elif position.quantity == broker_quantity:
            status = ReconciliationStatus.MATCHED
            detail = None
        else:
            status = ReconciliationStatus.DISCREPANCY
            detail = (
                f"internal quantity {position.quantity} does not match broker-reported "
                f"quantity {broker_quantity} (difference {position.quantity - broker_quantity})"
            )
            overall_status = ReconciliationStatus.DISCREPANCY

        lines.append(
            ReconciliationLine(
                instrument_id=instrument_id,
                internal_quantity=position.quantity,
                broker_reported_quantity=broker_quantity,
                status=status,
                discrepancy_detail=detail,
            )
        )

    run = ReconciliationRun(
        account_id=account_id,
        as_of=as_of,
        overall_status=overall_status,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.flush()
    for line in lines:
        line.reconciliation_run_id = run.id
        db.add(line)
    db.flush()
    return run, False


def reconcile_from_broker(
    db: Session,
    *,
    account_id: uuid.UUID,
    broker: PaperBrokerProvider,
    as_of: datetime,
    idempotency_key: str | None = None,
) -> tuple[ReconciliationRun, bool]:
    """Revision Prompt 16 idempotency review — "reconciliation is
    currently only manually triggered" was true in a second sense
    beyond the missing idempotency key: the only path in this codebase
    fetched broker-reported quantities via a *human-typed* request body
    (`routers/portfolio.py::reconcile_account`). `PaperBrokerProvider.get_paper_positions()`
    has existed since Revision Prompt 10 and was never wired to
    reconciliation — this function closes that gap by calling it
    directly, so no one has to manually copy numbers from a broker
    statement for a `PAPER_ALPACA` account. A ticker the broker reports
    that isn't in this app's instrument universe is skipped rather than
    erroring — an unknown symbol reconciling against nothing is a data
    gap to investigate separately, not a reason to fail the whole run."""
    broker_positions: dict[uuid.UUID, Decimal] = {}
    for position in broker.get_paper_positions():
        instrument = db.scalar(
            select(Instrument).where(Instrument.ticker == position["symbol"].upper())
        )
        if instrument is None:
            continue
        broker_positions[instrument.id] = Decimal(position["qty"])

    return run_reconciliation(
        db,
        account_id=account_id,
        as_of=as_of,
        broker_reported_positions=broker_positions,
        idempotency_key=idempotency_key,
    )
