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
    EarningsTimingCategory,
    RecommendationConfidence,
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
    """Revision Prompt R3 adds `verified_date`/`exchange_local_date`/
    `timing_category`/`verification_source`/`expected_report_period`/
    `confidence` — all nullable, additive columns supporting
    docs/HYBRID_EARNINGS_STRATEGY.md HES-2 condition 1 ("event time is
    verified"). `report_date`/`report_time` (free text) are unchanged
    for backward compatibility; `timing_category` is the closed-
    vocabulary version new code should prefer."""

    __tablename__ = "earnings_events"
    __table_args__ = (
        sa.Index("ix_earnings_events_lookup", "instrument_id", "report_date"),
        sa.Index("ix_earnings_events_report_date", "report_date"),
    )

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
    verified_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    exchange_local_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    timing_category: Mapped[EarningsTimingCategory] = mapped_column(
        sa.Enum(EarningsTimingCategory, name="earnings_timing_category"),
        default=EarningsTimingCategory.UNKNOWN,
    )
    verification_source: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    expected_report_period: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    confidence: Mapped[RecommendationConfidence | None] = mapped_column(
        sa.Enum(RecommendationConfidence, name="recommendation_confidence"), nullable=True
    )


class EarningsRevision(UUIDPkMixin, CreatedAtMixin, Base):
    """Fulfills Revision Prompt R3's "earnings_revision_snapshots" —
    this existing Phase 8 table already has that shape (a timestamped
    revision-in-time record); rather than create a duplicate table, R3
    adds the one missing provenance field (`ingested_at`) additively."""

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
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class EarningsConsensusSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "earnings_consensus_snapshots"
    __table_args__ = (
        sa.Index("ix_earnings_consensus_snapshots_lookup", "earnings_event_id", "as_of"),
    )

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id")
    )
    as_of: Mapped[date] = mapped_column(sa.Date)
    consensus_eps: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4), nullable=True)
    consensus_revenue: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    num_analysts: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    source: Mapped[str] = mapped_column(sa.String(40))
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class EarningsGuidanceItem(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "earnings_guidance_items"

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id"), index=True
    )
    metric: Mapped[str] = mapped_column(sa.String(30))
    guidance_low: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    guidance_high: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    period: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    source: Mapped[str] = mapped_column(sa.String(40))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class EarningsActual(UUIDPkMixin, CreatedAtMixin, Base):
    """The append-only, ground-truth record of a reported actual value.
    `usable_at` (Revision Prompt R3) is the timestamp this value became
    safely usable by any pre-event pipeline check — normally equal to
    `reported_at`, but may trail it slightly to account for propagation
    delay. `policy.earnings_evidence.assert_actual_not_leaked_into_pre_event_snapshot()`
    is the enforcement point that reads this field against a pre-event
    snapshot's `evidence_cutoff` (HES-7, no leakage from the future)."""

    __tablename__ = "earnings_actuals"
    __table_args__ = (sa.Index("ix_earnings_actuals_lookup", "earnings_event_id", "metric"),)

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id")
    )
    metric: Mapped[str] = mapped_column(sa.String(30))
    actual_value: Mapped[Decimal] = mapped_column(sa.Numeric(20, 4))
    reported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    usable_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    source: Mapped[str] = mapped_column(sa.String(40))
    ingested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class EarningsHistoricalGap(UUIDPkMixin, CreatedAtMixin, Base):
    """One historical post-earnings overnight/gap observation for an
    instrument — the input docs/HYBRID_EARNINGS_STRATEGY.md HES-5's
    gap-risk model draws its distribution from."""

    __tablename__ = "earnings_historical_gaps"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("instruments.id"), index=True
    )
    earnings_event_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id"), nullable=True
    )
    gap_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4))
    session_date: Mapped[date] = mapped_column(sa.Date)
    source: Mapped[str] = mapped_column(sa.String(40))


class EventExpectedMoveSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """A pre-event snapshot (Revision Prompt R3) — `evidence_cutoff` is
    the explicit, recorded boundary this snapshot respects, the same
    concept `earnings_feature_snapshots` uses, structurally distinct from
    any post-event table (HES-7 no-leakage requirement, "pre-event and
    post-event snapshots structurally distinguishable")."""

    __tablename__ = "event_expected_move_snapshots"
    __table_args__ = (
        sa.Index("ix_event_expected_move_snapshots_lookup", "earnings_event_id", "as_of"),
    )

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id")
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    evidence_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    atr_based_move_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    historical_gap_move_pct: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(10, 4), nullable=True
    )
    option_implied_move_pct: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(10, 4), nullable=True
    )
    selected_expected_move_pct: Mapped[Decimal] = mapped_column(sa.Numeric(10, 4))
    calculation_version: Mapped[str] = mapped_column(sa.String(20))


class EarningsFeatureSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """The pre-event, deterministic 8-factor earnings-direction score
    (docs/HYBRID_EARNINGS_STRATEGY.md HES-1) — always `is_pre_event=True`
    in this revision (no post-event equivalent writes this table; see
    `PostEarningsConfirmationSnapshot` instead, a structurally separate
    table, not a flag flip on this one). `linked_actual_id` is normally
    NULL — a true pre-event snapshot has no reason to reference a
    reported actual at all; the column exists specifically so
    `policy.earnings_evidence` has something concrete to validate against
    if it is ever set, catching a leakage bug rather than assuming one
    can't happen."""

    __tablename__ = "earnings_feature_snapshots"
    __table_args__ = (
        sa.Index("ix_earnings_feature_snapshots_lookup", "earnings_event_id", "as_of"),
    )

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id")
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    evidence_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    is_pre_event: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    component_price_trend: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    component_analyst_revisions: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(6, 4), nullable=True
    )
    component_options_skew: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    component_peer_reactions: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(6, 4), nullable=True
    )
    component_historical_drift: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(6, 4), nullable=True
    )
    component_guidance_momentum: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(6, 4), nullable=True
    )
    component_technical_setup: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(6, 4), nullable=True
    )
    component_sentiment: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    total_score: Mapped[Decimal] = mapped_column(sa.Numeric(4, 2))
    calculation_version: Mapped[str] = mapped_column(sa.String(20))
    linked_actual_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_actuals.id"), nullable=True
    )


class PostEarningsConfirmationSnapshot(UUIDPkMixin, CreatedAtMixin, Base):
    """The post-event counterpart to `EarningsFeatureSnapshot` — a
    structurally separate table (not the same table with a flag), per
    docs/HYBRID_EARNINGS_STRATEGY.md HES-4's three independent gates
    (reported results / forward guidance / market reaction), each
    recorded individually so a partial pass is never conflated with a
    full one."""

    __tablename__ = "post_earnings_confirmation_snapshots"
    __table_args__ = (
        sa.Index("ix_post_earnings_confirmation_snapshots_lookup", "earnings_event_id", "as_of"),
    )

    earnings_event_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("earnings_events.id")
    )
    as_of: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    evidence_cutoff: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    results_gate_passed: Mapped[bool] = mapped_column(sa.Boolean)
    guidance_gate_passed: Mapped[bool] = mapped_column(sa.Boolean)
    market_reaction_gate_passed: Mapped[bool] = mapped_column(sa.Boolean)
    all_gates_passed: Mapped[bool] = mapped_column(sa.Boolean)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


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
    "EarningsActual",
    "EarningsConsensusSnapshot",
    "EarningsEvent",
    "EarningsFeatureSnapshot",
    "EarningsGuidanceItem",
    "EarningsHistoricalGap",
    "EarningsRevision",
    "EventExpectedMoveSnapshot",
    "FundamentalsSnapshot",
    "MacroObservation",
    "MarketBar",
    "MarketRegimeSnapshot",
    "NewsItem",
    "NewsItemInstrument",
    "PostEarningsConfirmationSnapshot",
    "SentimentSnapshot",
    "TechnicalIndicatorSnapshot",
]
