from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON


class BacktestRun(Base):
    """A historical replay of the scoring engine (principle 14: no
    look-ahead bias, no survivorship bias, no unrealistic fills — see
    services/backtest.py and ADR-022..025). Runs synchronously — a
    `BacktestRun` row only ever exists in a complete state; a failed run
    persists nothing (same reasoning as ADR-006's job-queue deferral, no
    status enum needed).

    `parameters` is a full, versioned snapshot of every input (thresholds,
    `max_holding_days`, `position_size_pct`, `starting_cash`,
    `benchmark_ticker`) so a run is fully reproducible and auditable
    (principle 8/9) — these aren't part of `StrategyVersion.config`, which
    only holds scoring weights/thresholds, not backtest execution params.

    `results_summary` holds the report: ending equity, total return,
    max drawdown, win rate, trade log, and equity curve — see
    schemas/backtest.py for the typed shape callers see.
    """

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_version_id: Mapped[int] = mapped_column(sa.ForeignKey("strategy_versions.id"))
    date_range_start: Mapped[date] = mapped_column(sa.Date)
    date_range_end: Mapped[date] = mapped_column(sa.Date)
    parameters: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    results_summary: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
