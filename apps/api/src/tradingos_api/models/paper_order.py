from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base


class PaperOrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PaperOrderStatus(StrEnum):
    """DRAFT is ours alone — it means "proposed, not yet sent to Alpaca"
    (principle 11: nothing reaches the broker before explicit human
    confirmation). Every other status is derived from Alpaca's own
    (much more granular) order status — see
    providers/alpaca_paper_broker.py's status-mapping function."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class PaperOrder(Base):
    """The user's actual paper-trading activity (principle 9: an audited
    user action). Note the absence of a "linked_recommendation_id" column —
    `Recommendation` doesn't exist until Phase 4; that FK lands then, not as
    a column with no referent today.

    `PaperPosition` is *not* a table (see docs/DATA_DICTIONARY.md /
    ADR-013) — current holdings are derived from the sum of this table's
    FILLED/PARTIALLY_FILLED rows by services/portfolio.py, never stored
    separately.
    """

    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(sa.ForeignKey("paper_portfolios.id"))
    symbol_id: Mapped[int] = mapped_column(sa.ForeignKey("symbols.id"))

    side: Mapped[PaperOrderSide] = mapped_column(sa.Enum(PaperOrderSide, name="paper_order_side"))
    quantity: Mapped[int] = mapped_column(sa.Integer)
    order_type: Mapped[PaperOrderType] = mapped_column(
        sa.Enum(PaperOrderType, name="paper_order_type")
    )
    limit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    status: Mapped[PaperOrderStatus] = mapped_column(
        sa.Enum(PaperOrderStatus, name="paper_order_status")
    )

    # How many of `quantity` shares have actually filled so far — required
    # to correctly derive positions/cash for a PARTIALLY_FILLED order, where
    # `quantity` (requested) and the filled amount differ. 0 until confirmed.
    filled_quantity: Mapped[int] = mapped_column(sa.Integer, default=0)

    broker_order_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    filled_avg_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
