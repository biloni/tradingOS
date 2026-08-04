"""Backtesting (shipped MVP's `BacktestRun`, ADR-022..025, extended this
pass per ADR-043: `strategy_version_id` now points at the new UUID
`strategy_versions` table, and `BacktestTrade` normalizes what used to live
only inside `results_summary`'s JSON `trades` array into real, queryable
rows — the refinement brief's explicit ask.
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
from tradingos_api.models.enums import BacktestTradeExitReason


class BacktestRun(UUIDPkMixin, CreatedAtMixin, Base):
    """A historical replay of the scoring engine (principle 14: no
    look-ahead bias, no survivorship bias, no unrealistic fills — see
    services/backtest.py and ADR-022..025). Runs synchronously — a
    `BacktestRun` row only ever exists in a complete state; a failed run
    persists nothing.

    `results_summary` keeps the aggregate report (ending equity, total
    return, max drawdown, win rate, equity curve) as JSON — only the
    trade log is now also normalized into `BacktestTrade` rows below;
    `results_summary.trades` is retained for backward-compatible reads by
    `schemas/backtest.py`, not treated as two sources of truth (the
    normalized rows are generated from the same simulation output in the
    same write, never independently).
    """

    __tablename__ = "backtest_runs"

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("strategy_versions.id")
    )
    date_range_start: Mapped[date] = mapped_column(sa.Date)
    date_range_end: Mapped[date] = mapped_column(sa.Date)
    parameters: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    results_summary: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)


class BacktestTrade(UUIDPkMixin, CreatedAtMixin, Base):
    """One simulated trade from a backtest's trade log, normalized for
    direct querying (e.g. "every backtest trade on AAPL across all runs")
    without parsing `BacktestRun.results_summary`'s JSON."""

    __tablename__ = "backtest_trades"
    __table_args__ = (sa.Index("ix_backtest_trades_run", "backtest_run_id"),)

    backtest_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("backtest_runs.id")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    entry_date: Mapped[date] = mapped_column(sa.Date)
    entry_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    exit_date: Mapped[date] = mapped_column(sa.Date)
    exit_price: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(20, 8))
    pnl_usd: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    pnl_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4))
    exit_reason: Mapped[BacktestTradeExitReason] = mapped_column(
        sa.Enum(BacktestTradeExitReason, name="backtest_trade_exit_reason")
    )


__all__ = ["BacktestRun", "BacktestTrade"]
