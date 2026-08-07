from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class FeatureComponentEntry(BaseModel):
    component_key: str
    component_order: int
    value: Decimal | None
    status: str
    source: str
    detail: str | None
    calculation_version: str
    as_of: datetime


class TacticalScoreSnapshotResponse(BaseModel):
    id: uuid.UUID
    earnings_event_id: uuid.UUID
    as_of: datetime
    evidence_cutoff: datetime
    total_score: Decimal
    max_score: int = 8
    calculation_version: str
    components: list[FeatureComponentEntry]


class InvestmentQualitySnapshotResponse(BaseModel):
    id: uuid.UUID
    instrument_id: uuid.UUID
    as_of: date
    evidence_cutoff: datetime
    hard_disqualified: bool
    disqualification_reason: str | None
    calculation_version: str
    components: list[FeatureComponentEntry]


class PostEarningsConfirmationSnapshotResponse(BaseModel):
    id: uuid.UUID
    earnings_event_id: uuid.UUID
    as_of: datetime
    evidence_cutoff: datetime
    results_gate_passed: bool
    guidance_gate_passed: bool
    market_reaction_gate_passed: bool
    all_gates_passed: bool
    components: list[FeatureComponentEntry]
