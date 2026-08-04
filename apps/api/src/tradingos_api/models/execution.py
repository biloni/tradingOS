"""Portfolio & execution bounded context (ADR-043 supersedes
`models/paper_portfolio.py`/`models/paper_order.py`). Generalizes the
shipped MVP's Alpaca-specific paper trading into broker-agnostic
`Account`/`Order`/`Execution` tables that support both a manual journal
account and the existing Alpaca paper-broker account as two rows of the
same shape (ADR-039), plus real double-entry-style cash accounting
(`CashLedgerEntry`) and FIFO lot tracking (`PositionLot`) — neither of
which the shipped MVP's simple weighted-average derivation (ADR-013)
needed until now.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    AccountType,
    CashLedgerEntryType,
    FeeType,
    OrderLegRole,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    TradeStatus,
)


class Account(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    """One row per tracked portfolio. `MANUAL` is the primary
    journal-backed account (ADR-039); `PAPER_ALPACA` is the existing
    Alpaca paper-broker sandbox, now modeled here instead of its own
    bespoke `paper_portfolios` table. `broker_account_ref` is an
    *identifier* (e.g. Alpaca's own account id string), never a credential
    — the actual API key lives only in `apps/api/.env` (docs/SECURITY.md)."""

    __tablename__ = "accounts"

    account_type: Mapped[AccountType] = mapped_column(sa.Enum(AccountType, name="account_type"))
    name: Mapped[str] = mapped_column(sa.String(80))
    base_currency: Mapped[str] = mapped_column(sa.String(3), default="USD")
    starting_cash: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6), default=Decimal(10000))
    broker_account_ref: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class CashLedgerEntry(UUIDPkMixin, CreatedAtMixin, Base):
    """Append-only. Current cash for an account = `starting_cash` +
    `sum(amount)` over its ledger rows (positive = credit, negative =
    debit) — this is the actual "money/quantity precision" ledger the
    refinement brief asks to be invariant-tested (docs/TEST_EVIDENCE.md).
    `idempotency_key` lets a broker fill-event webhook (future phase) be
    replayed safely — the same key can only post once."""

    __tablename__ = "cash_ledger"
    __table_args__ = (sa.Index("ix_cash_ledger_account", "account_id", "occurred_at"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    entry_type: Mapped[CashLedgerEntryType] = mapped_column(
        sa.Enum(CashLedgerEntryType, name="cash_ledger_entry_type")
    )
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    related_order_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True
    )
    related_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)


class Position(UUIDPkMixin, TimestampMixin, Base):
    """The *current* aggregate for one (account, instrument) pair —
    quantity and weighted-average cost, maintained by the future
    portfolio service from `PositionLot` rows (never independently
    authoritative — same "derived, one source of truth" philosophy as the
    shipped MVP's ADR-013, just now backed by real lots instead of a
    live recompute over every fill). A flat position (quantity 0) may
    either persist or be removed — a service-layer choice documented in
    docs/DATA_DICTIONARY.md, not enforced by this schema."""

    __tablename__ = "positions"
    __table_args__ = (sa.UniqueConstraint("account_id", "instrument_id"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8), default=Decimal(0))
    avg_cost: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6), default=Decimal(0))
    opened_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class PositionLot(UUIDPkMixin, CreatedAtMixin, Base):
    """FIFO cost-basis tracking (the refinement brief's explicit ask,
    superseding the shipped MVP's simple weighted-average — ADR-013).
    `quantity_remaining` decreases as later closing executions consume this
    lot in open-date order; `quantity_opened` never changes once written
    (append-only fact about what this lot originally was)."""

    __tablename__ = "position_lots"
    __table_args__ = (
        sa.Index("ix_position_lots_open", "account_id", "instrument_id", "closed_at"),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("positions.id")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    opened_execution_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id")
    )
    quantity_opened: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    quantity_remaining: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    cost_basis_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    opened_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class Order(UUIDPkMixin, TimestampMixin, Base):
    """Supersedes `PaperOrder` (ADR-043) — same `DRAFT`-until-confirmed
    gate (ADR-014, principle 11), now against any `Account`, not just the
    Alpaca one. `idempotency_key` prevents a duplicate submit from a
    retried request (the refinement brief's "add uniqueness and
    idempotency keys ... for broker events")."""

    __tablename__ = "orders"

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    side: Mapped[OrderSide] = mapped_column(sa.Enum(OrderSide, name="order_side"))
    order_type: Mapped[OrderType] = mapped_column(sa.Enum(OrderType, name="order_type"))
    time_in_force: Mapped[TimeInForce] = mapped_column(
        sa.Enum(TimeInForce, name="time_in_force"), default=TimeInForce.DAY
    )
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    limit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(sa.Enum(OrderStatus, name="order_status"))
    broker_order_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    linked_recommendation_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendation_versions.id"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(100), unique=True, nullable=True)


class OrderLeg(UUIDPkMixin, CreatedAtMixin, Base):
    """Models bracket/OCO relationships without assuming a broker supports
    them: a `bracket_group_id` shared across a primary entry order plus its
    stop-loss and/or take-profit orders means our own domain logic treats
    them as one unit (e.g. canceling the primary cancels its siblings)
    regardless of whether any given `Account`'s broker natively links
    them. Every order gets exactly one `OrderLeg` row (role=`PRIMARY`,
    `bracket_group_id` NULL) unless it's part of a bracket."""

    __tablename__ = "order_legs"

    order_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("orders.id"), unique=True
    )
    role: Mapped[OrderLegRole] = mapped_column(
        sa.Enum(OrderLegRole, name="order_leg_role"), default=OrderLegRole.PRIMARY
    )
    bracket_group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)


class Execution(UUIDPkMixin, CreatedAtMixin, Base):
    """A fill (append-only fact). `broker_execution_id` is the idempotency
    key for a broker fill event — a replayed webhook/poll can't double-post
    the same execution twice."""

    __tablename__ = "executions"
    __table_args__ = (sa.Index("ix_executions_order", "order_id", "executed_at"),)

    order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("orders.id"))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    executed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    broker_execution_id: Mapped[str | None] = mapped_column(
        sa.String(100), unique=True, nullable=True
    )


class Fee(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "fees"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("executions.id"), index=True
    )
    fee_type: Mapped[FeeType] = mapped_column(sa.Enum(FeeType, name="fee_type"))
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))


class Trade(UUIDPkMixin, TimestampMixin, Base):
    """A round-trip: the span from a position opening from flat to
    returning to flat. `realized_pnl` is only set once `status=CLOSED`."""

    __tablename__ = "trades"

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    status: Mapped[TradeStatus] = mapped_column(sa.Enum(TradeStatus, name="trade_status"))
    opened_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    realized_pnl: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)


class TradeThesis(UUIDPkMixin, TimestampMixin, Base):
    """ADR-037's "intact thesis" concept anchors here — an add-on proposal's
    no-average-down precondition checks whether this thesis is still
    marked intact and whether a *new* catalyst exists beyond it."""

    __tablename__ = "trade_theses"

    trade_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("trades.id"))
    linked_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("recommendations.id"), nullable=True
    )
    thesis_text: Mapped[str] = mapped_column(sa.Text)
    catalyst_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    original_stop_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    is_intact: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class TradeNote(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "trade_notes"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("trades.id"), index=True
    )
    note_text: Mapped[str] = mapped_column(sa.Text)


class TradeAttachment(UUIDPkMixin, CreatedAtMixin, Base):
    """Metadata only — no file storage/upload exists in this pass
    (`storage_ref` is unpopulated until a future phase adds one)."""

    __tablename__ = "trade_attachments"

    trade_note_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("trade_notes.id"), index=True
    )
    file_name: Mapped[str] = mapped_column(sa.String(255))
    content_type: Mapped[str] = mapped_column(sa.String(100))
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    storage_ref: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)


class PortfolioSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (sa.UniqueConstraint("account_id", "as_of"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id")
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    cash: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    market_value: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    total_equity: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))


class RiskSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "risk_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("accounts.id"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    gross_exposure_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    largest_position_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    sector_concentration: Mapped[dict[str, Any] | None] = mapped_column(
        PORTABLE_JSON, nullable=True
    )
    correlation_flag: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    regime_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("market_regime_snapshots.id"), nullable=True
    )


__all__ = [
    "Account",
    "CashLedgerEntry",
    "Execution",
    "Fee",
    "Order",
    "OrderLeg",
    "Position",
    "PositionLot",
    "PortfolioSnapshot",
    "RiskSnapshot",
    "Trade",
    "TradeAttachment",
    "TradeNote",
    "TradeThesis",
]
