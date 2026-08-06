"""Provider diagnostics (Revision Prompt 4) — provider status, last
successful sync, data freshness by evidence category, earnings-calendar
verification queue, symbol quarantine, conflicting-source review, and
raw-to-normalized lineage. Read-only throughout — no ingestion is
triggered by any endpoint here (that is a scheduled-job concern, not a
diagnostics-dashboard concern)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.config import Settings, get_settings
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import DataQualityStatus, InstrumentValidationStatus
from tradingos_api.models.market_evidence import (
    DataQualityEvent,
    EarningsEvent,
    EarningsEventCorrection,
    FundamentalsSnapshot,
    MarketBar,
    NewsItem,
    ProviderIngestionRecord,
)
from tradingos_api.models.security_master import Instrument, InstrumentValidationEvent
from tradingos_api.providers.alpaca_evidence import (
    AlpacaBrokerCapabilityProvider,
    AlpacaCorporateActionsProvider,
    AlpacaInstrumentReferenceProvider,
    AlpacaNewsProvider,
    AlpacaStockDataProvider,
    AlpacaVolatilityIndexProvider,
)
from tradingos_api.providers.synthetic_evidence import (
    SyntheticAnalystRevisionProvider,
    SyntheticCompanyGuidanceProvider,
    SyntheticEarningsCalendarProvider,
    SyntheticEarningsConsensusProvider,
    SyntheticFundamentalsProvider,
    SyntheticMacroProvider,
    SyntheticOfficialFilingProvider,
    SyntheticOptionsExpectedMoveProvider,
)
from tradingos_api.schemas.provider_diagnostics import (
    ConflictingSourceEntry,
    EarningsCalendarQueueEntry,
    EvidenceFreshnessEntry,
    LastSyncEntry,
    LineageEntry,
    ProviderStatusEntry,
    SymbolQuarantineEntry,
)

router = APIRouter(prefix="/api/v1/provider-diagnostics", tags=["provider-diagnostics"])

_STALE_AFTER_SECONDS = 60 * 60 * 24 * 2  # 2 days — a simple, documented default


def _status_entry(interface: str, get_capabilities: object) -> ProviderStatusEntry:
    """`get_capabilities` is a zero-arg callable returning a
    `ProviderCapabilities` subclass — a plain function reference for a
    real provider constructor+capability-query in one step, so a
    `NotConfigured`/connection error surfaces as `is_configured=False`
    with the error message, never an unhandled 500."""
    try:
        capabilities = get_capabilities()  # type: ignore[operator]
        return ProviderStatusEntry(
            interface=interface,
            provider_name=capabilities.provider_name,
            is_live_data=capabilities.is_live_data,
            is_configured=True,
            capabilities=capabilities.model_dump(),
        )
    except Exception as exc:
        return ProviderStatusEntry(
            interface=interface,
            provider_name="unknown",
            is_live_data=False,
            is_configured=False,
            capabilities=None,
            error=str(exc),
        )


@router.get("/status", response_model=list[ProviderStatusEntry])
def get_provider_status(settings: Settings = Depends(get_settings)) -> list[ProviderStatusEntry]:
    return [
        _status_entry(
            "InstrumentReferenceProvider",
            lambda: AlpacaInstrumentReferenceProvider(settings).get_capabilities(),
        ),
        _status_entry(
            "MarketQuoteProvider", lambda: AlpacaStockDataProvider(settings).get_capabilities()
        ),
        _status_entry(
            "HistoricalBarsProvider",
            lambda: AlpacaStockDataProvider(settings).get_historical_bars_capabilities(),
        ),
        _status_entry(
            "CorporateActionsProvider",
            lambda: AlpacaCorporateActionsProvider(settings).get_capabilities(),
        ),
        _status_entry("NewsProvider", lambda: AlpacaNewsProvider(settings).get_capabilities()),
        _status_entry(
            "VolatilityIndexProvider",
            lambda: AlpacaVolatilityIndexProvider(settings).get_capabilities(),
        ),
        _status_entry(
            "BrokerCapabilityProvider",
            lambda: AlpacaBrokerCapabilityProvider(settings).get_capabilities(),
        ),
        _status_entry(
            "FundamentalsProvider", lambda: SyntheticFundamentalsProvider().get_capabilities()
        ),
        _status_entry(
            "EarningsCalendarProvider",
            lambda: SyntheticEarningsCalendarProvider().get_capabilities(),
        ),
        _status_entry(
            "EarningsConsensusProvider",
            lambda: SyntheticEarningsConsensusProvider().get_capabilities(),
        ),
        _status_entry(
            "AnalystRevisionProvider",
            lambda: SyntheticAnalystRevisionProvider().get_capabilities(),
        ),
        _status_entry(
            "CompanyGuidanceProvider",
            lambda: SyntheticCompanyGuidanceProvider().get_capabilities(),
        ),
        _status_entry(
            "OfficialFilingProvider", lambda: SyntheticOfficialFilingProvider().get_capabilities()
        ),
        _status_entry("MacroProvider", lambda: SyntheticMacroProvider().get_capabilities()),
        _status_entry(
            "OptionsExpectedMoveProvider",
            lambda: SyntheticOptionsExpectedMoveProvider().get_capabilities(),
        ),
    ]


@router.get("/last-sync", response_model=list[LastSyncEntry])
def get_last_sync(db: Session = Depends(get_db)) -> list[LastSyncEntry]:
    rows = db.execute(
        select(
            ProviderIngestionRecord.subject_type,
            ProviderIngestionRecord.source,
            func.max(ProviderIngestionRecord.ingested_at),
            func.count(),
        ).group_by(ProviderIngestionRecord.subject_type, ProviderIngestionRecord.source)
    ).all()
    return [
        LastSyncEntry(
            subject_type=subject_type,
            source=source,
            last_ingested_at=last_ingested_at,
            record_count=count,
        )
        for subject_type, source, last_ingested_at, count in rows
    ]


@router.get("/freshness", response_model=list[EvidenceFreshnessEntry])
def get_evidence_freshness(db: Session = Depends(get_db)) -> list[EvidenceFreshnessEntry]:
    now = datetime.now(UTC)
    categories: list[tuple[str, datetime | None]] = [
        ("market_bars", db.scalar(select(func.max(MarketBar.observed_at)))),
        ("news_items", db.scalar(select(func.max(NewsItem.usable_at)))),
        ("fundamentals_snapshots", db.scalar(select(func.max(FundamentalsSnapshot.usable_at)))),
    ]
    entries = []
    for category, most_recent in categories:
        age_seconds = (now - most_recent).total_seconds() if most_recent else None
        entries.append(
            EvidenceFreshnessEntry(
                evidence_category=category,
                most_recent_observed_at=most_recent,
                age_seconds=age_seconds,
                is_stale=(age_seconds is None or age_seconds > _STALE_AFTER_SECONDS),
            )
        )
    return entries


@router.get(
    "/earnings-calendar-verification-queue", response_model=list[EarningsCalendarQueueEntry]
)
def get_earnings_calendar_verification_queue(
    db: Session = Depends(get_db),
) -> list[EarningsCalendarQueueEntry]:
    """Every earnings event whose timing is not fully confirmed, or that
    has an open (unacknowledged) calendar-correction alert — the queue a
    human reviews before that event feeds any downstream decision."""
    needs_review_timings = {"UNKNOWN", "TIME_NOT_SUPPLIED", "DATE_UNCONFIRMED"}
    events = db.scalars(select(EarningsEvent)).all()
    entries: list[EarningsCalendarQueueEntry] = []
    for event in events:
        open_correction = db.scalar(
            select(EarningsEventCorrection).where(
                EarningsEventCorrection.earnings_event_id == event.id
            )
        )
        timing_value = event.timing_category.value
        reasons = []
        if timing_value in needs_review_timings:
            reasons.append(f"timing_category={timing_value}")
        if open_correction is not None:
            reasons.append("has a recorded calendar correction")
        if not reasons:
            continue
        inst = db.get(Instrument, event.instrument_id)
        assert inst is not None
        entries.append(
            EarningsCalendarQueueEntry(
                earnings_event_id=event.id,
                ticker=inst.ticker,
                report_date=event.report_date,
                timing_category=timing_value,
                reason="; ".join(reasons),
                has_open_correction_alert=open_correction is not None,
            )
        )
    return entries


@router.get("/symbol-quarantine", response_model=list[SymbolQuarantineEntry])
def get_symbol_quarantine(db: Session = Depends(get_db)) -> list[SymbolQuarantineEntry]:
    rows = db.scalars(
        select(InstrumentValidationEvent)
        .where(InstrumentValidationEvent.status == InstrumentValidationStatus.QUARANTINED)
        .order_by(InstrumentValidationEvent.created_at.desc())
    ).all()
    return [
        SymbolQuarantineEntry(
            id=row.id,
            raw_input=row.raw_input,
            status=row.status.value,
            reason=row.reason,
            source=row.source,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/conflicting-sources", response_model=list[ConflictingSourceEntry])
def get_conflicting_sources(db: Session = Depends(get_db)) -> list[ConflictingSourceEntry]:
    rows = db.scalars(
        select(DataQualityEvent)
        .where(DataQualityEvent.status == DataQualityStatus.CONFLICTING)
        .order_by(DataQualityEvent.detected_at.desc())
    ).all()
    return [
        ConflictingSourceEntry(
            id=row.id,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            detail=row.detail,
            detected_at=row.detected_at,
        )
        for row in rows
    ]


@router.get("/lineage/{subject_type}/{subject_id}", response_model=list[LineageEntry])
def get_lineage(
    subject_type: str, subject_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[LineageEntry]:
    rows = db.scalars(
        select(ProviderIngestionRecord)
        .where(
            ProviderIngestionRecord.subject_type == subject_type,
            ProviderIngestionRecord.subject_id == subject_id,
        )
        .order_by(ProviderIngestionRecord.ingested_at.asc())
    ).all()
    if not rows:
        raise HTTPException(
            status_code=404, detail="No ingestion lineage recorded for this subject."
        )
    return [
        LineageEntry(
            subject_type=row.subject_type,
            subject_id=subject_id,
            source=row.source,
            provider_record_id=row.provider_record_id,
            revision_id=row.revision_id,
            raw_payload_hash=row.raw_payload_hash,
            ingested_at=row.ingested_at,
        )
        for row in rows
    ]
