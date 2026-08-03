from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base


class AssetType(StrEnum):
    """Market universe is equities + ETFs only for the MVP (ADR-003)."""

    EQUITY = "EQUITY"
    ETF = "ETF"


class Symbol(Base):
    """The tradable instrument (master data, never carries transactional
    history — see docs/DATA_DICTIONARY.md)."""

    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(sa.String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    exchange: Mapped[str] = mapped_column(sa.String(20))
    asset_type: Mapped[AssetType] = mapped_column(sa.Enum(AssetType, name="asset_type"))
    active: Mapped[bool] = mapped_column(default=True)
