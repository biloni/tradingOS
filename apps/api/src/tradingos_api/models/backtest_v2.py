"""Event-driven backtest engine persistence (Revision Prompt 13).
Deliberately separate from the legacy `models/backtest.py`
(`BacktestRun`/`BacktestTrade`) rather than extending it — that table's
`strategy_version_id` FK points at the shipped-MVP's technical scoring-
weight-governance concept (`strategy_versions`), an orthogonal idea from
this revision's 8 fixed earnings-strategy variants, and its
`BacktestTradeExitReason` vocabulary (`SIGNAL_EXIT`/`MAX_HOLDING_DAYS`)
doesn't cover an explicit stop/target exit. See docs/DECISIONS.md's
Revision Prompt 13 ADR for the full reuse-vs-build-new reasoning.

`config` snapshots the complete `BacktestRunConfig` used to produce this
run (principle 8/9: full reproducibility) — the same pattern the legacy
`BacktestRun.parameters` already established. `results_summary` holds
the aggregate report (equity curve, `TradeStatsResult`, drawdown, Sharpe/
Sortino, etc.) computed by `services/performance_metrics.py` — the exact
same formula library Revision Prompt 12's live-portfolio metrics use
(ADR-062), never a second implementation for backtested trades.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    EventBacktestDatasetSplit,
    EventBacktestExitReason,
    EventBacktestStrategyKey,
    EventBacktestTradeLane,
)


class EventBacktestRun(UUIDPkMixin, CreatedAtMixin, Base):
    """One simulation of one strategy variant over one date range/split.
    Runs synchronously — a row only ever exists in a complete state; a
    failed run persists nothing (matching the legacy `BacktestRun`'s own
    ADR-024 convention)."""

    __tablename__ = "event_backtest_runs"

    strategy_key: Mapped[EventBacktestStrategyKey] = mapped_column(
        sa.Enum(EventBacktestStrategyKey, name="event_backtest_strategy_key")
    )
    dataset_split: Mapped[EventBacktestDatasetSplit] = mapped_column(
        sa.Enum(EventBacktestDatasetSplit, name="event_backtest_dataset_split"),
        default=EventBacktestDatasetSplit.FULL,
    )
    walk_forward_window_label: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    date_range_start: Mapped[date] = mapped_column(sa.Date)
    date_range_end: Mapped[date] = mapped_column(sa.Date)
    config: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    results_summary: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    is_golden_regression: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    """Flags the one locked baseline-reproduction run
    (`tests/test_backtest_engine_golden.py` asserts against a run created
    with this flag) — distinguishes it from the many validation-grid/
    walk-forward runs the same engine also produces."""


class EventBacktestTrade(UUIDPkMixin, CreatedAtMixin, Base):
    """One simulated trade from a run's trade log, normalized for direct
    querying — mirrors the legacy `BacktestTrade`'s own normalization
    rationale. `earnings_event_id` is intentionally NOT a foreign key:
    the backtest's synthetic multi-year event universe
    (`services/backtest_data.py`) does not correspond to real
    `EarningsEvent` rows (ADR-024's "never write simulated data into a
    real transactional table" principle, applied here to earnings events
    the same way it already applies to orders) — `event_date`/
    `fiscal_period` carry the same drill-down context as plain columns
    instead."""

    __tablename__ = "event_backtest_trades"

    backtest_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("event_backtest_runs.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    lane: Mapped[EventBacktestTradeLane] = mapped_column(
        sa.Enum(EventBacktestTradeLane, name="event_backtest_trade_lane")
    )
    event_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    entry_date: Mapped[date] = mapped_column(sa.Date)
    entry_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    exit_date: Mapped[date] = mapped_column(sa.Date)
    exit_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    fees_usd: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    pnl_usd: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    """Net of `fees_usd` — the fee is already subtracted, never a
    separate figure the caller must remember to net out."""
    pnl_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4))
    exit_reason: Mapped[EventBacktestExitReason] = mapped_column(
        sa.Enum(EventBacktestExitReason, name="event_backtest_exit_reason")
    )
    score: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    expected_move_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)


__all__ = ["EventBacktestRun", "EventBacktestTrade"]
