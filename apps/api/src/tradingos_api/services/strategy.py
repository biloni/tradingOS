from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.strategy_version import StrategyVersion

DEFAULT_CONFIG: dict[str, Any] = {
    "weights": {"trend": 1.0, "momentum": 1.0, "macd": 1.0, "bollinger": 1.0},
    "rsi_bullish_low": 50,
    "rsi_bullish_high": 70,
    "rsi_oversold": 30,
}


def get_or_create_default_strategy_version(session: Session) -> StrategyVersion:
    """The MVP has exactly one active `StrategyVersion`, lazily created on
    first use (same pattern as Phase 3's `get_or_create_default_portfolio`).
    This is the *first* version, not a proposed change, so it doesn't go
    through Phase 6's not-yet-built strategy-change approval gate
    (principle 16)."""
    strategy = session.execute(
        select(StrategyVersion).where(StrategyVersion.is_active.is_(True))
    ).scalar_one_or_none()
    if strategy is not None:
        return strategy

    strategy = StrategyVersion(
        name="Plan of Record v1",
        config=DEFAULT_CONFIG,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return strategy
