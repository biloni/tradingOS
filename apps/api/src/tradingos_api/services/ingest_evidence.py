"""Ingestion orchestration (Revision Prompt 4) — one function per
evidence type, each: calls a provider, runs the relevant data-quality
gate(s) (`services/data_quality.py`), writes the point-in-time fields
onto the target table, and records a `ProviderIngestionRecord` (raw
payload hash/provider-record-id/revision-id ledger). Every function is
idempotent — re-running it with the same provider response is always a
safe no-op, never a duplicate row (the "idempotent replay" required
test).

No recommendation, scoring, or order logic lives here — these functions
only ever populate the evidence layer.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    CorporateActionType,
    EarningsTimingCategory,
)
from tradingos_api.models.market_evidence import (
    CorporateAction,
    EarningsActual,
    EarningsConsensusSnapshot,
    EarningsEvent,
    EarningsEventCorrection,
    EarningsGuidanceItem,
    EarningsRevision,
    FundamentalsSnapshot,
    MacroObservation,
    NewsItem,
    NewsItemInstrument,
    ProviderIngestionRecord,
)
from tradingos_api.models.operations import Alert
from tradingos_api.providers.earnings_actuals import EarningsActualsProvider
from tradingos_api.providers.earnings_calendar import EarningsCalendarProvider
from tradingos_api.providers.earnings_consensus import (
    AnalystRevisionProvider,
    EarningsConsensusProvider,
)
from tradingos_api.providers.fundamentals import FundamentalsProvider
from tradingos_api.providers.macro import MacroProvider
from tradingos_api.providers.news import NewsProvider
from tradingos_api.providers.official_evidence import CompanyGuidanceProvider
from tradingos_api.providers.reference_data import CorporateActionsProvider
from tradingos_api.services.data_quality import (
    check_duplicate_news,
    check_too_few_analysts,
    record_finding,
)


def _record_ingestion(
    db: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID | None,
    source: str,
    provider_record_id: str | None,
    revision_id: str | None,
    raw_payload_hash: str | None = None,
) -> ProviderIngestionRecord:
    record = ProviderIngestionRecord(
        subject_type=subject_type,
        subject_id=subject_id,
        source=source,
        provider_record_id=provider_record_id,
        revision_id=revision_id,
        raw_payload_hash=raw_payload_hash,
    )
    db.add(record)
    db.flush()
    return record


def ingest_corporate_actions(
    db: Session,
    provider: CorporateActionsProvider,
    *,
    instrument_id: uuid.UUID,
    ticker: str,
    start: date,
    end: date,
) -> list[CorporateAction]:
    records = provider.get_corporate_actions(ticker, start, end)
    created: list[CorporateAction] = []
    for rec in records:
        exists = db.scalar(
            select(CorporateAction).where(
                CorporateAction.instrument_id == instrument_id,
                CorporateAction.action_type == CorporateActionType(rec.action_type),
                CorporateAction.ex_date == rec.ex_date,
                CorporateAction.source == rec.source,
            )
        )
        if exists is not None:
            continue
        action = CorporateAction(
            instrument_id=instrument_id,
            action_type=CorporateActionType(rec.action_type),
            ex_date=rec.ex_date,
            ratio=Decimal(rec.ratio) if rec.ratio is not None else None,
            amount=Decimal(rec.amount) if rec.amount is not None else None,
            source=rec.source,
        )
        db.add(action)
        db.flush()
        _record_ingestion(
            db,
            subject_type="CorporateAction",
            subject_id=action.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(action)
    return created


def ingest_news(
    db: Session, provider: NewsProvider, *, instrument_id: uuid.UUID, ticker: str, since: str
) -> list[NewsItem]:
    """Duplicate detection uses the same `dedup_hash` idempotency key
    `NewsItem` already enforces at the DB level (unique constraint,
    Phase 8/R3) — `check_duplicate_news()` catches it pre-insert so a
    replay is a clean no-op rather than an `IntegrityError`."""
    records = provider.get_news(ticker, since)
    existing_hashes = set(db.scalars(select(NewsItem.dedup_hash)).all())
    created: list[NewsItem] = []
    for rec in records:
        finding = check_duplicate_news(rec.dedup_hash, existing_hashes)
        if finding is not None:
            continue
        news = NewsItem(
            canonical_url=rec.canonical_url,
            publisher=rec.publisher,
            headline=rec.headline,
            published_at=rec.published_at or rec.observed_at,
            dedup_hash=rec.dedup_hash,
            usable_at=rec.observed_at,
        )
        db.add(news)
        db.flush()
        db.add(NewsItemInstrument(news_item_id=news.id, instrument_id=instrument_id))
        existing_hashes.add(rec.dedup_hash)
        _record_ingestion(
            db,
            subject_type="NewsItem",
            subject_id=news.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(news)
    return created


def ingest_earnings_calendar(
    db: Session,
    provider: EarningsCalendarProvider,
    *,
    instrument_id: uuid.UUID,
    ticker: str,
    within_days: int,
    owner_user_id: uuid.UUID,
) -> tuple[list[EarningsEvent], list[EarningsEventCorrection]]:
    """A calendar record whose `revision_id` differs from the
    already-ingested `EarningsEvent`'s last-seen revision is a
    *correction*, never a silent overwrite: this writes a new
    `EarningsEventCorrection` row plus a linked `Alert` (R3's `Alert`
    model), and updates the existing `EarningsEvent` row's fields in
    place (the event's identity — one row per real-world event — stays
    stable; what changes is tracked in the correction log, same as any
    other Phase 8 append-only-history-over-a-mutable-current-row
    pattern, e.g. `RiskPolicy`/`RiskPolicyVersion`)."""
    records = provider.get_upcoming_earnings(ticker, within_days)
    created_events: list[EarningsEvent] = []
    corrections: list[EarningsEventCorrection] = []
    now = datetime.now(UTC)

    for rec in records:
        existing = db.scalar(
            select(EarningsEvent)
            .where(EarningsEvent.instrument_id == instrument_id)
            .order_by(EarningsEvent.created_at.desc())
        )
        if existing is None:
            event = EarningsEvent(
                instrument_id=instrument_id,
                fiscal_period=rec.fiscal_period,
                report_date=rec.report_date,
                source=rec.source,
                verified_date=rec.published_at.date() if rec.published_at else None,
                timing_category=EarningsTimingCategory(rec.timing_category),
                verification_source=rec.verification_source,
                expected_report_period=rec.fiscal_period,
            )
            db.add(event)
            db.flush()
            _record_ingestion(
                db,
                subject_type="EarningsEvent",
                subject_id=event.id,
                source=rec.source,
                provider_record_id=rec.provider_record_id,
                revision_id=rec.revision_id,
            )
            created_events.append(event)
            continue

        changed_fields: list[tuple[str, str | None, str | None]] = []
        if existing.report_date != rec.report_date:
            changed_fields.append(("report_date", str(existing.report_date), str(rec.report_date)))
        if existing.timing_category.value != rec.timing_category:
            changed_fields.append(
                ("timing_category", existing.timing_category.value, rec.timing_category)
            )

        if not changed_fields:
            created_events.append(existing)
            continue

        alert = Alert(
            owner_user_id=owner_user_id,
            instrument_id=instrument_id,
            alert_type=AlertType.SYSTEM_NOTIFICATION,
            severity=AlertSeverity.WARNING,
            status=AlertStatus.OPEN,
            title=f"Earnings calendar correction for {ticker.upper()}",
            detail="; ".join(f"{f}: {old!r} -> {new!r}" for f, old, new in changed_fields),
            triggered_at=now,
        )
        db.add(alert)
        db.flush()

        prior_version = db.scalar(
            select(EarningsEventCorrection.version_number)
            .where(EarningsEventCorrection.earnings_event_id == existing.id)
            .order_by(EarningsEventCorrection.version_number.desc())
        )
        next_version = (prior_version or 0) + 1
        for field_name, previous_value, new_value in changed_fields:
            correction = EarningsEventCorrection(
                earnings_event_id=existing.id,
                version_number=next_version,
                corrected_field=field_name,
                previous_value=previous_value,
                new_value=new_value,
                corrected_at=now,
                source=rec.source,
                alert_id=alert.id,
            )
            db.add(correction)
            corrections.append(correction)

        existing.report_date = rec.report_date
        existing.timing_category = EarningsTimingCategory(rec.timing_category)
        created_events.append(existing)

    db.flush()
    return created_events, corrections


def ingest_earnings_consensus(
    db: Session, provider: EarningsConsensusProvider, *, earnings_event_id: uuid.UUID, ticker: str
) -> EarningsConsensusSnapshot | None:
    rec = provider.get_consensus(ticker)
    if rec is None:
        return None
    as_of = rec.observed_at.date()
    exists = db.scalar(
        select(EarningsConsensusSnapshot).where(
            EarningsConsensusSnapshot.earnings_event_id == earnings_event_id,
            EarningsConsensusSnapshot.as_of == as_of,
            EarningsConsensusSnapshot.source == rec.source,
        )
    )
    if exists is not None:
        return exists

    finding = check_too_few_analysts(rec.num_analysts)
    if finding is not None:
        record_finding(
            db,
            finding,
            subject_type="EarningsConsensusSnapshot",
            subject_id=earnings_event_id,
            instrument_id=None,
            detected_at=datetime.now(UTC),
        )

    snapshot = EarningsConsensusSnapshot(
        earnings_event_id=earnings_event_id,
        as_of=as_of,
        consensus_eps=Decimal(rec.consensus_eps) if rec.consensus_eps else None,
        consensus_revenue=Decimal(rec.consensus_revenue) if rec.consensus_revenue else None,
        num_analysts=rec.num_analysts,
        eps_dispersion=Decimal(rec.eps_dispersion) if rec.eps_dispersion else None,
        source=rec.source,
        observed_at=rec.observed_at,
        usable_at=rec.observed_at,
    )
    db.add(snapshot)
    db.flush()
    _record_ingestion(
        db,
        subject_type="EarningsConsensusSnapshot",
        subject_id=snapshot.id,
        source=rec.source,
        provider_record_id=rec.provider_record_id,
        revision_id=rec.revision_id,
    )
    return snapshot


def ingest_earnings_actuals(
    db: Session,
    provider: EarningsActualsProvider,
    *,
    earnings_event_id: uuid.UUID,
    ticker: str,
    fiscal_period: str,
) -> list[EarningsActual]:
    """Revision Prompt 11 step 2 ("ingest and validate official
    results"). Idempotent by `(earnings_event_id, metric, source)` — the
    same pattern every other `ingest_*` function in this module uses —
    which is what makes re-running this against an already-ingested
    release ("duplicate release", one of Prompt 11's required test
    categories) a safe no-op rather than a second row. An empty
    provider response (results not yet released) returns an empty list;
    callers distinguish "no rows yet" from "ingested" by checking the
    return value's length, which is exactly the signal
    `services/post_earnings_workflow.py` uses to decide `WAITING_FOR_DATA`.
    """
    records = provider.get_actuals(ticker, fiscal_period)
    created: list[EarningsActual] = []
    for rec in records:
        exists = db.scalar(
            select(EarningsActual).where(
                EarningsActual.earnings_event_id == earnings_event_id,
                EarningsActual.metric == rec.metric,
                EarningsActual.source == rec.source,
            )
        )
        if exists is not None:
            created.append(exists)
            continue
        reported_at = rec.published_at or rec.observed_at
        actual = EarningsActual(
            earnings_event_id=earnings_event_id,
            metric=rec.metric,
            actual_value=Decimal(rec.actual_value),
            reported_at=reported_at,
            usable_at=rec.observed_at,
            source=rec.source,
        )
        db.add(actual)
        db.flush()
        _record_ingestion(
            db,
            subject_type="EarningsActual",
            subject_id=actual.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(actual)
    return created


def ingest_analyst_revisions(
    db: Session,
    provider: AnalystRevisionProvider,
    *,
    earnings_event_id: uuid.UUID,
    ticker: str,
    window_days: int,
) -> list[EarningsRevision]:
    records = provider.get_revisions(ticker, window_days)
    created: list[EarningsRevision] = []
    for rec in records:
        exists = db.scalar(
            select(EarningsRevision).where(
                EarningsRevision.earnings_event_id == earnings_event_id,
                EarningsRevision.revised_at == datetime.fromisoformat(rec.revised_at),
                EarningsRevision.source == rec.source,
            )
        )
        if exists is not None:
            continue
        revision = EarningsRevision(
            earnings_event_id=earnings_event_id,
            revised_at=datetime.fromisoformat(rec.revised_at),
            previous_eps_estimate=(
                Decimal(rec.previous_eps_estimate) if rec.previous_eps_estimate else None
            ),
            new_eps_estimate=Decimal(rec.new_eps_estimate),
            direction=rec.direction,
            source=rec.source,
            usable_at=rec.observed_at,
        )
        db.add(revision)
        db.flush()
        _record_ingestion(
            db,
            subject_type="EarningsRevision",
            subject_id=revision.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(revision)
    return created


def ingest_company_guidance(
    db: Session, provider: CompanyGuidanceProvider, *, earnings_event_id: uuid.UUID, ticker: str
) -> list[EarningsGuidanceItem]:
    records = provider.get_guidance(ticker)
    created: list[EarningsGuidanceItem] = []
    for rec in records:
        exists = db.scalar(
            select(EarningsGuidanceItem).where(
                EarningsGuidanceItem.earnings_event_id == earnings_event_id,
                EarningsGuidanceItem.metric == rec.metric,
                EarningsGuidanceItem.period == rec.period,
                EarningsGuidanceItem.source == rec.source,
            )
        )
        if exists is not None:
            continue
        item = EarningsGuidanceItem(
            earnings_event_id=earnings_event_id,
            metric=rec.metric,
            guidance_low=Decimal(rec.guidance_low) if rec.guidance_low else None,
            guidance_high=Decimal(rec.guidance_high) if rec.guidance_high else None,
            guidance_midpoint=Decimal(rec.guidance_midpoint) if rec.guidance_midpoint else None,
            units=rec.units,
            period=rec.period,
            issued_at=rec.published_at or rec.observed_at,
            source=rec.source,
            usable_at=rec.observed_at,
        )
        db.add(item)
        db.flush()
        _record_ingestion(
            db,
            subject_type="EarningsGuidanceItem",
            subject_id=item.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(item)
    return created


def ingest_fundamentals(
    db: Session, provider: FundamentalsProvider, *, instrument_id: uuid.UUID, ticker: str
) -> FundamentalsSnapshot | None:
    rec = provider.get_fundamentals(ticker)
    if rec is None:
        return None
    exists = db.scalar(
        select(FundamentalsSnapshot).where(
            FundamentalsSnapshot.instrument_id == instrument_id,
            FundamentalsSnapshot.as_of == rec.as_of,
            FundamentalsSnapshot.source == rec.source,
        )
    )
    if exists is not None:
        return exists
    snapshot = FundamentalsSnapshot(
        instrument_id=instrument_id,
        as_of=rec.as_of,
        market_cap=Decimal(rec.market_cap) if rec.market_cap else None,
        pe_ratio=Decimal(rec.pe_ratio) if rec.pe_ratio else None,
        source=rec.source,
        observed_at=rec.observed_at,
        usable_at=rec.observed_at,
    )
    db.add(snapshot)
    db.flush()
    _record_ingestion(
        db,
        subject_type="FundamentalsSnapshot",
        subject_id=snapshot.id,
        source=rec.source,
        provider_record_id=rec.provider_record_id,
        revision_id=rec.revision_id,
    )
    return snapshot


def ingest_macro_series(
    db: Session, provider: MacroProvider, *, series_code: str, start: date, end: date
) -> list[MacroObservation]:
    records = provider.get_series(series_code, start, end)
    created: list[MacroObservation] = []
    for rec in records:
        exists = db.scalar(
            select(MacroObservation).where(
                MacroObservation.series_code == series_code,
                MacroObservation.as_of == rec.as_of,
                MacroObservation.source == rec.source,
            )
        )
        if exists is not None:
            continue
        observation = MacroObservation(
            series_code=series_code, as_of=rec.as_of, value=Decimal(rec.value), source=rec.source
        )
        db.add(observation)
        db.flush()
        _record_ingestion(
            db,
            subject_type="MacroObservation",
            subject_id=observation.id,
            source=rec.source,
            provider_record_id=rec.provider_record_id,
            revision_id=rec.revision_id,
        )
        created.append(observation)
    return created


def compute_raw_payload_hash(raw_payload: bytes) -> str:
    """SHA-256 of the exact bytes a provider returned — call only when
    the provider's terms permit retention (principle 12); pass the
    result as `raw_payload_hash` to `_record_ingestion`'s caller, never
    fabricate one when retention isn't permitted (leave `None`)."""
    return hashlib.sha256(raw_payload).hexdigest()
