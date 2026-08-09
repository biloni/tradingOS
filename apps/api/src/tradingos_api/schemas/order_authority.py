from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    ApprovalInvalidationReason,
    BrokerSubmissionOutcome,
    EnvironmentLabel,
    LotLane,
    OrderApprovalStatus,
    OrderAuthorityMode,
    OrderProposalStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    RecommendationMode,
    TimeInForce,
)
from tradingos_api.schemas.instruments import InstrumentResponse


class OrderProposalCreateRequest(BaseModel):
    recommendation_version_id: uuid.UUID
    account_id: uuid.UUID
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    max_notional: Decimal | None = None
    rationale: str | None = None
    idempotency_key: str | None = None


class OrderProposalVersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    time_in_force: TimeInForce
    max_notional: Decimal | None
    rationale: str | None

    model_config = {"from_attributes": True}


class OrderProposalResponse(BaseModel):
    id: uuid.UUID
    recommendation_version_id: uuid.UUID
    account_id: uuid.UUID
    instrument: InstrumentResponse
    mode: RecommendationMode
    side: OrderSide
    status: OrderProposalStatus
    latest_version: OrderProposalVersionResponse


class OrderConfirmationInput(BaseModel):
    """Mirrors `policy.order_authority.OrderConfirmation` — a human
    confirmation immediately preceding this one policy-evaluation call."""

    confirmed_at: datetime
    account_id: str
    environment: str
    broker_endpoint: str


class AutoPolicyGrantInput(BaseModel):
    """Mirrors `policy.order_authority.AutoPolicyGrant`."""

    policy_version: str
    enabled: bool


class OrderPolicyEvaluationRequest(BaseModel):
    requested_mode: OrderAuthorityMode
    is_live: bool = False
    confirmation: OrderConfirmationInput | None = None
    auto_policy: AutoPolicyGrantInput | None = None


class OrderPolicyEvaluationResponse(BaseModel):
    id: uuid.UUID
    order_proposal_version_id: uuid.UUID
    evaluated_at: datetime
    requested_mode: OrderAuthorityMode
    authorized: bool
    denial_reason: str | None

    model_config = {"from_attributes": True}


class ApprovalBoundFieldsResponse(BaseModel):
    account_id: uuid.UUID
    instrument_id: uuid.UUID
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Decimal | None
    stop_price: Decimal | None
    time_in_force: TimeInForce
    outside_hours: bool
    attached_legs: dict[str, Any]
    max_notional: Decimal | None
    recommendation_version_id: uuid.UUID | None
    quote_price_at_approval: Decimal | None = None

    model_config = {"from_attributes": True}


class OrderApprovalCreateRequest(BaseModel):
    order_proposal_version_id: uuid.UUID
    approved_by: str | None = None
    expires_in_seconds: int = 300
    outside_hours: bool = False
    attached_legs: dict[str, Any] = {}


class OrderApprovalResponse(BaseModel):
    id: uuid.UUID
    order_proposal_version_id: uuid.UUID
    approved_by: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime
    status: OrderApprovalStatus
    integrity_hash: str
    bound_fields: ApprovalBoundFieldsResponse


class OrderApprovalDecisionRequest(BaseModel):
    approved_by: str | None = None


class OrderApprovalInvalidateRequest(BaseModel):
    reason: ApprovalInvalidationReason
    detail: str | None = None


class PreSubmissionSnapshotResponse(BaseModel):
    """ORDER FLOW steps 2-4 — "refresh... recalculate... display the
    complete entry and protective exits," always fresh at read time,
    never a cached value from proposal- or approval-creation time."""

    quote_price: Decimal | None
    quote_observed_at: datetime | None
    buying_power: Decimal
    open_position_quantity: Decimal
    open_order_count: int
    is_trading_day: bool
    market_closed_reason: str | None
    upcoming_earnings_report_date: str | None
    requires_reapproval: bool
    reason: str | None


class OrderSubmitRequest(BaseModel):
    """`POST /order-approvals/{id}/submit` — ORDER FLOW step 7. Bracket
    prices are never taken from this request: they were already bound
    into `ApprovalBoundFields.attached_legs` at approval time
    (`{"take_profit_price": "...", "stop_loss_price": "..."}`), so a
    submit call cannot silently change what was approved."""

    requested_mode: OrderAuthorityMode
    confirmation: OrderConfirmationInput | None = None
    lane: LotLane = LotLane.UNCLASSIFIED
    source_recommendation_version_id: uuid.UUID | None = None
    emulation_acknowledged: bool = False


class BrokerSubmissionAttemptResponse(BaseModel):
    id: uuid.UUID
    order_approval_id: uuid.UUID
    attempted_at: datetime
    environment_label: EnvironmentLabel
    outcome: BrokerSubmissionOutcome
    idempotency_key: str | None
    detail: str | None
    resulting_order_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class OrderSubmitResponse(BaseModel):
    attempt: BrokerSubmissionAttemptResponse
    order_id: uuid.UUID | None
    order_status: OrderStatus | None
    invalidated: bool
    invalidation_reason: str | None
    used_native_bracket: bool
    disclosure: str | None
    stop_loss_order_id: uuid.UUID | None
    take_profit_order_id: uuid.UUID | None


class KillSwitchActivateRequest(BaseModel):
    activated_by: str
    reason: str | None = None


class CancelOpenOrdersRequest(BaseModel):
    account_id: uuid.UUID | None = None
    triggered_by: str
    reason: str | None = None


class CancelOpenOrdersResponse(BaseModel):
    orders_canceled_count: int
    canceled_order_ids: list[uuid.UUID]
