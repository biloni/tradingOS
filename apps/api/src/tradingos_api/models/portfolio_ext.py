"""Portfolio extensions (Revision Prompt 8): corrections-through-
reversal, corporate-action application, CSV import, and reconciliation
— none of which the Phase 8 `models/execution.py` schema had a home
for. Kept in a separate module from `execution.py` for the same reason
`models/order_authority.py` is separate from `execution.py`'s `Order`/
`Execution`: this is a distinct bounded concern (portfolio bookkeeping
operations) layered on top of, not mixed into, the base ledger schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import ImportRowStatus, ReconciliationStatus


class ExecutionCorrection(UUIDPkMixin, CreatedAtMixin, Base):
    """ "Never silently delete or rewrite an executed event" — a
    correction is always a new, real `Execution` row with a negated
    quantity (`reversal_execution_id`), linked back to the
    `original_execution_id` it corrects. The original row is untouched;
    both rows remain in `executions` forever, and this table is the
    append-only record of *why* the reversal exists."""

    __tablename__ = "execution_corrections"

    original_execution_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id"), index=True
    )
    reversal_execution_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id"), unique=True
    )
    reason: Mapped[str] = mapped_column(sa.Text)
    corrected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class CorporateActionApplication(UUIDPkMixin, CreatedAtMixin, Base):
    """Applying a `CorporateAction` (the Revision Prompt 4 evidence-layer
    fact — a split ratio or a dividend amount) to one account's lots is
    its own append-only record, keyed so the same corporate action can
    never be double-applied to the same account
    (`idempotency_key = f"{corporate_action_id}:{account_id}"`).
    `quantity_before`/`quantity_after` capture a split's effect on the
    account's aggregate `Position.quantity`; `cash_credit_amount`/
    `cash_ledger_entry_id` capture a dividend's cash effect — a merger or
    spinoff (no numeric ratio/amount this schema models yet) is recorded
    with both null and a human-readable `detail`."""

    __tablename__ = "corporate_action_applications"

    corporate_action_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("corporate_actions.id"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    applied_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    quantity_before: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 8), nullable=True)
    quantity_after: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 8), nullable=True)
    cash_credit_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    cash_ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("cash_ledger.id"), nullable=True
    )
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(sa.String(140), unique=True)


class ImportBatch(UUIDPkMixin, CreatedAtMixin, Base):
    """One CSV import attempt. `idempotency_key` (a hash of the file's
    raw bytes, computed by the caller) means re-uploading the exact same
    file is a no-op at the batch level before any row is even parsed —
    the per-row `dedup_key` on `ImportRow` additionally protects against
    two *different* files containing an overlapping fill."""

    __tablename__ = "import_batches"

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    source_filename: Mapped[str] = mapped_column(sa.String(255))
    imported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(sa.Integer)
    idempotency_key: Mapped[str] = mapped_column(sa.String(64), unique=True)


class ImportRow(UUIDPkMixin, CreatedAtMixin, Base):
    """One row of a CSV import. `dedup_key` (account + instrument + side
    + quantity + price + executed_at, hashed) is unique *within an
    account* — importing the same logical fill twice, whether from the
    same file re-uploaded or two files with overlapping rows, produces a
    `DUPLICATE_SKIPPED` row here rather than a second `Execution`.

    The uniqueness is a **partial** index — only over rows whose
    `status = 'IMPORTED'`. At most one row may ever hold the "this fill
    was actually applied" claim for a given `(account_id, dedup_key)`,
    but multiple `DUPLICATE_SKIPPED` audit rows are legitimate (the same
    file uploaded three times should show three attempts, not fail on
    the second one trying to record its own skip)."""

    __tablename__ = "import_rows"
    __table_args__ = (
        sa.Index(
            "ix_import_rows_unique_imported",
            "account_id",
            "dedup_key",
            unique=True,
            postgresql_where=sa.text("status = 'IMPORTED'"),
        ),
    )

    import_batch_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("import_batches.id"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    row_number: Mapped[int] = mapped_column(sa.Integer)
    raw_line: Mapped[str] = mapped_column(sa.Text)
    dedup_key: Mapped[str] = mapped_column(sa.String(64))
    status: Mapped[ImportRowStatus] = mapped_column(
        sa.Enum(ImportRowStatus, name="import_row_status")
    )
    resulting_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id"), nullable=True
    )
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ReconciliationRun(UUIDPkMixin, CreatedAtMixin, Base):
    """One reconciliation pass for one account at one point in time —
    "broker aggregate position reconciliation." `overall_status` is
    `DISCREPANCY` iff any `ReconciliationLine` under it is."""

    __tablename__ = "reconciliation_runs"

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    overall_status: Mapped[ReconciliationStatus] = mapped_column(
        sa.Enum(ReconciliationStatus, name="reconciliation_status")
    )


class ReconciliationLine(UUIDPkMixin, CreatedAtMixin, Base):
    """Per-instrument comparison: the internally-derived aggregate
    quantity (`sum(PositionLot.quantity_remaining)`, lane-blind — a
    broker only ever reports one combined position) versus what the
    broker reports. A `MANUAL` account has no broker feed to compare
    against; `broker_reported_quantity` stays `NULL` and `status` is
    always `MATCHED` for it (nothing to reconcile, not silently treated
    as a discrepancy)."""

    __tablename__ = "reconciliation_lines"

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("reconciliation_runs.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    internal_quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    broker_reported_quantity: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 8), nullable=True
    )
    status: Mapped[ReconciliationStatus] = mapped_column(
        sa.Enum(ReconciliationStatus, name="reconciliation_status")
    )
    discrepancy_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


__all__ = [
    "CorporateActionApplication",
    "ExecutionCorrection",
    "ImportBatch",
    "ImportRow",
    "ReconciliationLine",
    "ReconciliationRun",
]
