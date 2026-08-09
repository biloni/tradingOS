from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    AccountType,
    ImportRowStatus,
    LotLane,
    OrderSide,
    ReconciliationStatus,
    ThesisStatus,
)
from tradingos_api.schemas.instruments import InstrumentResponse


class AccountResponse(BaseModel):
    id: uuid.UUID
    account_type: AccountType
    name: str
    base_currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    instrument: InstrumentResponse
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal | None


class CashSummaryResponse(BaseModel):
    account_id: uuid.UUID
    cash: Decimal
    starting_cash: Decimal


class RiskSnapshotResponse(BaseModel):
    as_of: datetime
    gross_exposure_pct: Decimal | None
    largest_position_pct: Decimal | None
    sector_concentration: dict[str, Any] | None
    correlation_flag: bool

    model_config = {"from_attributes": True}


class AccountDetailResponse(BaseModel):
    account: AccountResponse
    cash: CashSummaryResponse
    positions: list[PositionResponse]
    latest_risk_snapshot: RiskSnapshotResponse | None


# ---------------------------------------------------------------------------
# Revision Prompt 8 — lane attribution, holding guidance, corrections,
# CSV import, reconciliation.
# ---------------------------------------------------------------------------


class SubpositionResponse(BaseModel):
    lane: LotLane
    quantity: Decimal
    avg_cost: Decimal
    lot_count: int


class PositionLotResponse(BaseModel):
    id: uuid.UUID
    lane: LotLane
    quantity_opened: Decimal
    quantity_remaining: Decimal
    cost_basis_price: Decimal
    opened_at: datetime
    closed_at: datetime | None
    source_recommendation_version_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class InvestmentHoldingGuidanceResponse(BaseModel):
    lot_id: uuid.UUID
    current_action: str | None
    thesis_health: ThesisStatus | None
    valuation_context: str | None
    accumulation_zone: str | None
    next_review_date: date | None
    upcoming_earnings_date: date | None
    portfolio_role: str | None
    portfolio_weight_pct: Decimal | None


class TacticalHoldingGuidanceResponse(BaseModel):
    lot_id: uuid.UUID
    current_action: str | None
    setup_and_event_phase: str | None
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_prices: list[Decimal]
    time_exit_review_date: date | None
    invalidation_conditions: list[str]
    upcoming_event_date: date | None
    open_alert_titles: list[str]
    linked_order_proposal_status: str | None


class LotWithGuidanceResponse(BaseModel):
    lot: PositionLotResponse
    investment_guidance: InvestmentHoldingGuidanceResponse | None
    tactical_guidance: TacticalHoldingGuidanceResponse | None


class PositionDetailResponse(BaseModel):
    """ "Show combined broker position and separate analytical
    subpositions" plus per-lot holding guidance — the position-detail
    screen's one response."""

    instrument: InstrumentResponse
    combined_quantity: Decimal
    combined_avg_cost: Decimal
    subpositions: list[SubpositionResponse]
    lots: list[LotWithGuidanceResponse]


class ManualFillRequest(BaseModel):
    side: OrderSide
    ticker: str
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    lane: LotLane = LotLane.UNCLASSIFIED
    source_recommendation_version_id: uuid.UUID | None = None


class ManualFillResponse(BaseModel):
    execution_id: uuid.UUID
    position_id: uuid.UUID
    realized_pnl: Decimal
    trade_id: uuid.UUID | None
    lane_selection_is_certain: bool


class ImportRowResponse(BaseModel):
    row_number: int
    status: ImportRowStatus
    resulting_execution_id: uuid.UUID | None
    error_detail: str | None

    model_config = {"from_attributes": True}


class ImportBatchResponse(BaseModel):
    id: uuid.UUID
    source_filename: str
    imported_at: datetime
    row_count: int
    was_duplicate_batch: bool
    rows: list[ImportRowResponse]


class ReconciliationLineResponse(BaseModel):
    instrument: InstrumentResponse
    internal_quantity: Decimal
    broker_reported_quantity: Decimal | None
    status: ReconciliationStatus
    discrepancy_detail: str | None


class ReconciliationRunResponse(BaseModel):
    id: uuid.UUID
    as_of: datetime
    overall_status: ReconciliationStatus
    lines: list[ReconciliationLineResponse]


class ReconciliationRequest(BaseModel):
    broker_reported_positions: dict[str, Decimal] = {}  # ticker -> quantity
