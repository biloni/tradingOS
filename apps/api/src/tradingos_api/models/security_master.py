"""Security master & watchlists bounded context (ADR-043 supersedes
`models/symbol.py`'s `Symbol` with `Instrument`; ADR-032/033 add symbol
validation and tiered watchlists as first-class entities)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.mixins import CreatedAtMixin, OwnedMixin, TimestampMixin, UUIDPkMixin
from tradingos_api.models.enums import AssetType, InstrumentValidationStatus, MonitoringFrequency


class Sector(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "sectors"

    name: Mapped[str] = mapped_column(sa.String(80), unique=True)


class Industry(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "industries"

    sector_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("sectors.id"))
    name: Mapped[str] = mapped_column(sa.String(120))


class Instrument(UUIDPkMixin, TimestampMixin, Base):
    """Supersedes the shipped MVP's `Symbol` (ADR-043) — master data, never
    carries transactional history. `ticker` is the canonical, validated
    symbol; a raw user-entered string that doesn't resolve to one never
    becomes a row here (see `InstrumentValidationEvent`)."""

    __tablename__ = "instruments"

    ticker: Mapped[str] = mapped_column(sa.String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    exchange: Mapped[str] = mapped_column(sa.String(20))
    asset_type: Mapped[AssetType] = mapped_column(sa.Enum(AssetType, name="asset_type"))
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("industries.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class InstrumentAlias(UUIDPkMixin, CreatedAtMixin, Base):
    """An alternate string the same instrument is known by (a prior ticker
    after a rename, a different exchange's listing symbol) — lets symbol
    validation (ADR-032) resolve a raw input to the *current* canonical
    instrument even when the user typed an outdated or alternate symbol."""

    __tablename__ = "instrument_aliases"
    __table_args__ = (sa.UniqueConstraint("alias", "alias_type"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    alias: Mapped[str] = mapped_column(sa.String(20))
    alias_type: Mapped[str] = mapped_column(sa.String(30))


class InstrumentValidationEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """ADR-032 — append-only. `raw_input` is preserved verbatim regardless
    of outcome (principle 3/4); a `QUARANTINED` row has
    `canonical_instrument_id = NULL` and a human-readable `reason`."""

    __tablename__ = "instrument_validation_events"

    raw_input: Mapped[str] = mapped_column(sa.String(20), index=True)
    status: Mapped[InstrumentValidationStatus] = mapped_column(
        sa.Enum(InstrumentValidationStatus, name="instrument_validation_status")
    )
    canonical_instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.String(40))
    checked_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class Watchlist(UUIDPkMixin, OwnedMixin, TimestampMixin, Base):
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(sa.String(80))
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class WatchlistItem(UUIDPkMixin, TimestampMixin, Base):
    """ADR-033 — decoupled from `Instrument` master data. Membership
    requires a resolved/ambiguous/quarantined validation record to exist
    for the instrument (enforced in the future watchlist service, not the
    schema — a `QUARANTINED` instrument can still be a member row so it
    stays visible as "wanted but not usable", per FR-08)."""

    __tablename__ = "watchlist_items"
    __table_args__ = (sa.UniqueConstraint("watchlist_id", "instrument_id"),)

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("watchlists.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    tier: Mapped[int] = mapped_column(sa.Integer, default=1)
    priority: Mapped[int] = mapped_column(sa.Integer, default=0)
    active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    monitoring_frequency: Mapped[MonitoringFrequency] = mapped_column(
        sa.Enum(MonitoringFrequency, name="monitoring_frequency"), default=MonitoringFrequency.DAILY
    )
    added_at: Mapped[date] = mapped_column(sa.Date)


__all__ = [
    "Industry",
    "Instrument",
    "InstrumentAlias",
    "InstrumentValidationEvent",
    "Sector",
    "Watchlist",
    "WatchlistItem",
]
