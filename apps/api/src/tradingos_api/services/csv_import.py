"""CSV fill import (Revision Prompt 8). Documented format — one header
row followed by data rows:

    executed_at,side,ticker,quantity,price,lane
    2026-01-15T14:30:00Z,BUY,MRVL,100,75.00,TACTICAL

`lane` is optional (blank/omitted -> `UNCLASSIFIED`). Every row becomes
a real `Execution` applied through `services/portfolio_accounting.py` —
this module's own job is strictly the idempotent batch/row bookkeeping
around that, never the accounting math itself.

**Import idempotency, two layers:** `ImportBatch.idempotency_key` (a
hash of the raw file bytes) makes re-uploading the exact same file a
no-op before any row is parsed; `ImportRow.dedup_key` (a hash of
account + ticker + side + quantity + price + executed_at) additionally
catches the same logical fill arriving via two different files with
overlapping rows — each row's fate is visible afterward as `IMPORTED`,
`DUPLICATE_SKIPPED`, or `ERROR`, never silently dropped.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import ImportRowStatus, LotLane, OrderSide, OrderStatus, OrderType
from tradingos_api.models.execution import Execution, Order
from tradingos_api.models.portfolio_ext import ImportBatch, ImportRow
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.portfolio_accounting import InsufficientLotsError, apply_execution

CALCULATION_VERSION = "v1"

REQUIRED_COLUMNS = ("executed_at", "side", "ticker", "quantity", "price")


def compute_file_idempotency_key(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _row_dedup_key(
    account_id: uuid.UUID, ticker: str, side: str, quantity: str, price: str, executed_at: str
) -> str:
    canonical = f"{account_id}|{ticker}|{side}|{quantity}|{price}|{executed_at}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ImportOutcome:
    batch: ImportBatch
    rows: list[ImportRow]
    was_duplicate_batch: bool


def import_execution_csv(
    db: Session,
    *,
    account_id: uuid.UUID,
    filename: str,
    file_bytes: bytes,
    imported_at: datetime,
) -> ImportOutcome:
    idempotency_key = compute_file_idempotency_key(file_bytes)
    existing_batch = db.scalar(
        select(ImportBatch).where(ImportBatch.idempotency_key == idempotency_key)
    )
    if existing_batch is not None:
        rows = list(
            db.scalars(
                select(ImportRow).where(ImportRow.import_batch_id == existing_batch.id)
            ).all()
        )
        return ImportOutcome(batch=existing_batch, rows=rows, was_duplicate_batch=True)

    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not set(REQUIRED_COLUMNS).issubset(set(reader.fieldnames)):
        raise ValueError(f"CSV must contain columns: {', '.join(REQUIRED_COLUMNS)}")

    raw_rows = list(reader)
    batch = ImportBatch(
        account_id=account_id,
        source_filename=filename,
        imported_at=imported_at,
        row_count=len(raw_rows),
        idempotency_key=idempotency_key,
    )
    db.add(batch)
    db.flush()

    import_rows: list[ImportRow] = []
    for row_number, raw_row in enumerate(raw_rows, start=1):
        import_rows.append(_import_one_row(db, account_id, batch.id, row_number, raw_row))

    return ImportOutcome(batch=batch, rows=import_rows, was_duplicate_batch=False)


def _import_one_row(
    db: Session,
    account_id: uuid.UUID,
    batch_id: uuid.UUID,
    row_number: int,
    raw_row: dict[str, str],
) -> ImportRow:
    raw_line = ",".join(f"{k}={v}" for k, v in raw_row.items())
    dedup_key = _row_dedup_key(
        account_id,
        raw_row.get("ticker", ""),
        raw_row.get("side", ""),
        raw_row.get("quantity", ""),
        raw_row.get("price", ""),
        raw_row.get("executed_at", ""),
    )

    existing = db.scalar(
        select(ImportRow).where(
            ImportRow.account_id == account_id,
            ImportRow.dedup_key == dedup_key,
            ImportRow.status == ImportRowStatus.IMPORTED,
        )
    )
    if existing is not None:
        row = ImportRow(
            import_batch_id=batch_id,
            account_id=account_id,
            row_number=row_number,
            raw_line=raw_line,
            dedup_key=dedup_key,
            status=ImportRowStatus.DUPLICATE_SKIPPED,
        )
        db.add(row)
        db.flush()
        return row

    # A savepoint per row: if `apply_execution` (or parsing) fails partway
    # through, the Order/Execution rows already flushed for *this row*
    # must not survive as orphans with no matching lot/cash effect —
    # roll back to the savepoint, not just catch-and-continue.
    savepoint = db.begin_nested()
    try:
        ticker = raw_row["ticker"].strip().upper()
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
        if instrument is None:
            raise ValueError(f"unknown ticker: {ticker}")
        side = OrderSide(raw_row["side"].strip().upper())
        quantity = Decimal(raw_row["quantity"].strip())
        price = Decimal(raw_row["price"].strip())
        executed_at = datetime.fromisoformat(raw_row["executed_at"].strip().replace("Z", "+00:00"))
        lane_raw = (raw_row.get("lane") or "").strip().upper()
        lane = LotLane(lane_raw) if lane_raw else LotLane.UNCLASSIFIED

        order = Order(
            account_id=account_id,
            instrument_id=instrument.id,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            status=OrderStatus.FILLED,
        )
        db.add(order)
        db.flush()
        execution = Execution(
            order_id=order.id, quantity=quantity, price=price, executed_at=executed_at
        )
        db.add(execution)
        db.flush()

        apply_execution(
            db,
            execution=execution,
            account_id=account_id,
            instrument_id=instrument.id,
            side=side,
            lane=lane,
        )
        savepoint.commit()

        row = ImportRow(
            import_batch_id=batch_id,
            account_id=account_id,
            row_number=row_number,
            raw_line=raw_line,
            dedup_key=dedup_key,
            status=ImportRowStatus.IMPORTED,
            resulting_execution_id=execution.id,
        )
    except (ValueError, InvalidOperation, KeyError, InsufficientLotsError) as exc:
        savepoint.rollback()
        row = ImportRow(
            import_batch_id=batch_id,
            account_id=account_id,
            row_number=row_number,
            raw_line=raw_line,
            dedup_key=dedup_key,
            status=ImportRowStatus.ERROR,
            error_detail=str(exc),
        )
    db.add(row)
    db.flush()
    return row
