from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON


class StrategyVersion(Base):
    """A versioned, user-approved configuration of scoring weights/thresholds
    (principle 8 — configurable, never hardcoded). The MVP has exactly one
    active version, lazily created by
    services/strategy.py's get_or_create_default_strategy_version() — this is
    the *first* version, not a proposed change, so it doesn't go through
    Phase 6's not-yet-built strategy-change approval gate (principle 16).

    `config` shape (see services/scoring.py for the consumer):
    {"weights": {"trend": 1.0, "momentum": 1.0, "macd": 1.0, "bollinger": 1.0},
     "rsi_bullish_low": 50, "rsi_bullish_high": 70, "rsi_oversold": 30}
    """

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100))
    config: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
