from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.models.enums import (
    ApprovalInvalidationReason,
    OrderApprovalStatus,
    OrderAuthorityMode,
    OrderProposalStatus,
    OrderSide,
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
