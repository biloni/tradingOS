from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class ProviderStatusEntry(BaseModel):
    interface: str
    provider_name: str
    is_live_data: bool
    is_configured: bool
    capabilities: dict[str, Any] | None
    error: str | None = None


class LastSyncEntry(BaseModel):
    subject_type: str
    source: str
    last_ingested_at: datetime
    record_count: int


class EvidenceFreshnessEntry(BaseModel):
    evidence_category: str
    most_recent_observed_at: datetime | None
    age_seconds: float | None
    is_stale: bool


class EarningsCalendarQueueEntry(BaseModel):
    earnings_event_id: uuid.UUID
    ticker: str
    report_date: date
    timing_category: str
    reason: str
    has_open_correction_alert: bool


class SymbolQuarantineEntry(BaseModel):
    id: uuid.UUID
    raw_input: str
    status: str
    reason: str
    source: str
    created_at: datetime


class ConflictingSourceEntry(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID | None
    detail: str
    detected_at: datetime


class LineageEntry(BaseModel):
    subject_type: str
    subject_id: uuid.UUID
    source: str
    provider_record_id: str | None
    revision_id: str | None
    raw_payload_hash: str | None
    ingested_at: datetime
