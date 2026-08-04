"""Market evidence bounded context (ADR-043 supersedes `models/price_bar.py`
and `models/indicator.py`; the rest are new — docs/PRODUCT_REQUIREMENTS.md
FR-10-FR-15). Every evidence table carries source + as-of/observed time +
ingestion time (+ quality status where the value can legitimately be
uncertain) — principle 3's provenance envelope, extended beyond price data
to every new evidence type.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON
from tradingos_api.db.mixins import CreatedAtMixin, UUIDPkMixin
from tradingos_api.models.enums import (
    CorporateActionType,
    DataQualityStatus,
    EarningsRevisionDirection,
    RegimeClassification,
    Timeframe,
)


class MarketBar(UUIDPkMixin, CreatedAtMixin, Base):
    """Supersedes `PriceBar` (ADR-043). Still append-only, still no unique
    constraint on `(instrument_id, as_of, timeframe)` (ADR-011's reasoning
    carries over unchanged: a later corrective re-fetch is a new row, not
    an update) — `ingested_at` (this row's own `created_at`) is what a
    "latest observation" query orders by, same as the shipped MVP's
    `fetched_at` did."""

    __tablename__ = "market_bars"
    __table_args__ = (sa.Index("ix_market_bars_lookup", "instrument_id", "as_of", "timeframe"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    timeframe: Mapped[Timeframe] = mapped_column(sa.Enum(Timeframe, name="timeframe"))
    open: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    volume: Mapped[int] = mapped_column(sa.BigInteger)
    adjusted: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    source: Mapped[str] = mapped_column(sa.String(40))
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class CorporateAction(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "corporate_actions"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    action_type: Mapped[CorporateActionType] = mapped_column(
        sa.Enum(CorporateActionType, name="corporate_action_type")
    )
    ex_date: Mapped[date] = mapped_column(sa.Date)
    ratio: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(40))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class TechnicalIndicatorSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """Supersedes `Indicator` (ADR-043) — same idempotent-by-formula-version
    semantics as the shipped MVP (ADR-012), unchanged."""

    __tablename__ = "technical_indicator_snapshots"
    __table_args__ = (sa.UniqueConstraint("instrument_id", "as_of", "indicator_name", "version"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    indicator_name: Mapped[str] = mapped_column(sa.String(20))
    version: Mapped[str] = mapped_column(sa.String(10), default="v1")
    value: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))


class FundamentalsSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "fundamentals_snapshots"
    __table_args__ = (sa.Index("ix_fundamentals_lookup", "instrument_id", "as_of"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    market_cap: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("sectors.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(sa.String(40))
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    quality_status: Mapped[DataQualityStatus] = mapped_column(
        sa.Enum(DataQualityStatus, name="data_quality_status"), default=DataQualityStatus.OK
    )


class EarningsEvent(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "earnings_events"
    __table_args__ = (sa.Index("ix_earnings_events_lookup", "instrument_id", "report_date"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    fiscal_period: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    report_date: Mapped[date] = mapped_column(sa.Date)
    report_time: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    eps_estimate: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    eps_actual: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(40))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class EarningsRevision(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "earnings_revisions"

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id"), index=True
    )
    revised_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    previous_eps_estimate: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    new_eps_estimate: Mapped[Decimal] = mapped_column(sa.Numeric(12, 4))
    direction: Mapped[EarningsRevisionDirection] = mapped_column(
        sa.Enum(EarningsRevisionDirection, name="earnings_revision_direction")
    )
    source: Mapped[str] = mapped_column(sa.String(40))


class NewsItem(UUIDPkMixin, CreatedAtMixin, Base):
    """`dedup_hash` (e.g. a hash of canonical_url + publisher + headline) is
    the idempotency key for provider ingestion — re-ingesting the same
    story is a safe no-op (unique constraint), mirroring the shipped MVP's
    `Indicator` idempotency pattern (ADR-012) applied to a new evidence
    type. `license_metadata` records what the licensing vendor's terms
    permit (e.g. display-only vs. re-publishable) — principle 12."""

    __tablename__ = "news_items"

    canonical_url: Mapped[str] = mapped_column(sa.String(500), index=True)
    publisher: Mapped[str] = mapped_column(sa.String(100))
    headline: Mapped[str] = mapped_column(sa.String(500))
    published_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    dedup_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    license_metadata: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)


class NewsItemInstrument(UUIDPkMixin, CreatedAtMixin, Base):
    """Many-to-many: one story can mention several tracked instruments."""

    __tablename__ = "news_item_instruments"
    __table_args__ = (sa.UniqueConstraint("news_item_id", "instrument_id"),)

    news_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("news_items.id"), index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )


class SentimentSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """Phase 2 evidence type (docs/MVP_PLAN.md — no sentiment vendor
    selected yet, BLOCKING_DECISIONS.md #1); modeled now so the schema
    doesn't need a migration once a vendor is chosen."""

    __tablename__ = "sentiment_snapshots"
    __table_args__ = (sa.Index("ix_sentiment_snapshots_lookup", "instrument_id", "as_of"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id")
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 4))
    source: Mapped[str] = mapped_column(sa.String(40))
    sample_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class MacroObservation(UUIDPkMixin, CreatedAtMixin, Base):
    """VIX-proxy bars (BLOCKING_DECISIONS.md #2) and any other macro series
    land here, keyed by a free-text `series_code` rather than a closed
    enum — the set of tracked macro series is expected to grow."""

    __tablename__ = "macro_observations"
    __table_args__ = (sa.UniqueConstraint("series_code", "as_of", "source"),)

    series_code: Mapped[str] = mapped_column(sa.String(40), index=True)
    as_of: Mapped[date] = mapped_column(sa.Date)
    value: Mapped[Decimal] = mapped_column(sa.Numeric(18, 6))
    source: Mapped[str] = mapped_column(sa.String(40))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class MarketRegimeSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """ADR-034 — one row per day, `inputs_snapshot` captures the exact
    numbers the classification was derived from (FR-03) so "why was today
    conservative" is always answerable from stored data."""

    __tablename__ = "market_regime_snapshots"
    __table_args__ = (sa.UniqueConstraint("as_of"),)

    as_of: Mapped[date] = mapped_column(sa.Date)
    classification: Mapped[RegimeClassification] = mapped_column(
        sa.Enum(RegimeClassification, name="regime_classification")
    )
    vix_proxy_level: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    vix_percentile: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    vix_rate_of_change: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 6), nullable=True)
    breadth_pct_above_sma50: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON, default=dict)


class DataQualityEvent(UUIDPkMixin, CreatedAtMixin, Base):
    """A generic, cross-evidence-type quality flag — same "record_type +
    ref_id" generic-log shape as `AuditEvent` (ADR-015's reasoning applies
    identically: one quality log spans many different evidence tables)."""

    __tablename__ = "data_quality_events"
    __table_args__ = (sa.Index("ix_data_quality_events_subject", "subject_type", "subject_id"),)

    subject_type: Mapped[str] = mapped_column(sa.String(50))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(as_uuid=True), nullable=True)
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=True
    )
    status: Mapped[DataQualityStatus] = mapped_column(
        sa.Enum(DataQualityStatus, name="data_quality_status")
    )
    detail: Mapped[str] = mapped_column(sa.Text)
    detected_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


__all__ = [
    "CorporateAction",
    "DataQualityEvent",
    "EarningsEvent",
    "EarningsRevision",
    "FundamentalsSnapshot",
    "MacroObservation",
    "MarketBar",
    "MarketRegimeSnapshot",
    "NewsItem",
    "NewsItemInstrument",
    "SentimentSnapshot",
    "TechnicalIndicatorSnapshot",
]
