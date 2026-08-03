from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base


class IndicatorName(StrEnum):
    SMA_20 = "SMA_20"
    SMA_50 = "SMA_50"
    EMA_12 = "EMA_12"
    EMA_26 = "EMA_26"
    RSI_14 = "RSI_14"
    MACD_LINE = "MACD_LINE"
    MACD_SIGNAL = "MACD_SIGNAL"
    MACD_HIST = "MACD_HIST"
    BB_UPPER = "BB_UPPER"
    BB_MID = "BB_MID"
    BB_LOWER = "BB_LOWER"
    ATR_14 = "ATR_14"


class Indicator(Base):
    """A deterministic calculation derived from `PriceBar` (principle 2/6).
    Idempotent, not append-only: given the same inputs and the same formula
    `version`, the output never changes, so `(symbol_id, as_of,
    indicator_name, version)` is unique — recomputing is insert-if-not-exists,
    never an update. A formula change bumps `version`; it never rewrites
    history under the old version string."""

    __tablename__ = "indicators"
    __table_args__ = (
        sa.UniqueConstraint(
            "symbol_id", "as_of", "indicator_name", "version", name="uq_indicator_identity"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(sa.ForeignKey("symbols.id"))
    as_of: Mapped[date] = mapped_column(sa.Date)
    indicator_name: Mapped[IndicatorName] = mapped_column(
        sa.Enum(IndicatorName, name="indicator_name")
    )
    version: Mapped[str] = mapped_column(sa.String(10))
    value: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
