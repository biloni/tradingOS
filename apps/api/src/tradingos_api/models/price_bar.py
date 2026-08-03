from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base


class Timeframe(StrEnum):
    """Only DAY is used in Phase 2 — intraday is out of scope (2-10 day
    swing-trade horizon, not day-trading)."""

    DAY = "DAY"


class PriceBar(Base):
    """An observed market fact (principle 2/3). Append-only: never mutated
    in place — a correction is a new row with a later `fetched_at`, not an
    update. `get_latest_price_bars()` (services/price_bars.py) is the one
    place every caller reads the "current" value through, picking the
    max-`fetched_at` row per (symbol, as_of, timeframe)."""

    __tablename__ = "price_bars"
    __table_args__ = (sa.Index("ix_price_bars_symbol_asof_tf", "symbol_id", "as_of", "timeframe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(sa.ForeignKey("symbols.id"))
    as_of: Mapped[date] = mapped_column(sa.Date)
    timeframe: Mapped[Timeframe] = mapped_column(sa.Enum(Timeframe, name="timeframe"))

    open: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    volume: Mapped[int] = mapped_column(sa.BigInteger)

    source: Mapped[str] = mapped_column(sa.String(50))
    adjustment: Mapped[str] = mapped_column(sa.String(20))
    fetched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
