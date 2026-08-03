from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base


class PaperPortfolio(Base):
    """One row per configurable paper portfolio (master data). The MVP uses
    exactly one, lazily created by
    services/portfolio.py's get_or_create_default_portfolio() — no seed
    script needed for a single row.

    `starting_cash_usd` is the only cash figure stored; current cash is
    always derived (services/portfolio.py's get_portfolio_snapshot()) from
    `starting_cash_usd` plus/minus filled `PaperOrder` rows — never stored
    directly, so it can never drift out of sync with the order history.
    """

    __tablename__ = "paper_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    starting_cash_usd: Mapped[Decimal] = mapped_column(
        sa.Numeric(18, 2), default=Decimal("10000.00")
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
