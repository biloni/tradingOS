from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON


class StrategyVersionStatus(StrEnum):
    """A real lifecycle (Phase 6), replacing a bare `is_active: bool` —
    one source of truth for "is this the active version," matching this
    codebase's recurring derived-state philosophy (`PaperPosition`/
    ADR-013, `get_latest_price_bars()`/ADR-011).

    PROPOSED: a candidate config, not yet reviewed.
    ACTIVE: the version `services/scoring.py`'s `compute_score()` is
      currently configured by (`get_or_create_default_strategy_version()`
      resolves to whichever row has this status — exactly one at a time).
    REJECTED: reviewed and declined; never activates.
    SUPERSEDED: was previously ACTIVE, replaced by a newer approval —
      kept for history, never deleted (same "supersede, don't delete"
      pattern as `RecommendationStatus`).
    """

    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class StrategyVersion(Base):
    """A versioned configuration of scoring weights/thresholds (principle 8
    — configurable, never hardcoded). The MVP's very first version is
    lazily created by services/strategy.py's
    `get_or_create_default_strategy_version()` directly as ACTIVE — it's
    the first version, not a proposed change, so it skips the approval
    gate. Every subsequent change goes through Phase 6's propose → compare
    → approve/reject flow (principle 16): `services/strategy.py`'s
    `propose_strategy_version()`, `run_comparison()`,
    `approve_strategy_version()`, `reject_strategy_version()`.

    `decided_at`/`decision_comment` are set once, when a PROPOSED version
    is approved or rejected — both stay `None` while still PROPOSED, and
    are never touched again afterward (in particular, a version moving
    ACTIVE -> SUPERSEDED does not update its own `decided_at`; that field
    records the decision *about this version*, not later consequences of
    a different version's approval).

    `config` shape (see services/scoring.py for the consumer):
    {"weights": {"trend": 1.0, "momentum": 1.0, "macd": 1.0, "bollinger": 1.0},
     "rsi_bullish_low": 50, "rsi_bullish_high": 70, "rsi_oversold": 30}
    """

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100))
    config: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    status: Mapped[StrategyVersionStatus] = mapped_column(
        sa.Enum(StrategyVersionStatus, name="strategy_version_status")
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
