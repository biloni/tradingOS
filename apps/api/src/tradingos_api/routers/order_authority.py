"""Order-proposal creation, policy evaluation, and approval decisions
(Revision Prompt R3, ADR-048) — extended by Revision Prompt 10 with the
two endpoints that actually reach a **paper-only** broker:
`GET /order-approvals/{id}/refresh` (ORDER FLOW steps 2-4, a preview a
client calls before showing the confirm button) and
`POST /order-approvals/{id}/submit` (step 7, the only HTTP route in this
codebase that calls `services/order_execution.py`, itself the only
caller of a `PaperBrokerProvider`). Through R3/Revision Prompt 9, an
`OrderApproval` reaching `APPROVED` was this router's final state —
nothing wrote a `BrokerSubmissionAttempt`; that boundary is now real,
still exclusively paper (`services/order_authority.py::assert_broker_boundary_is_paper()`
fails closed on anything else).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.core.dependencies import (
    get_broker_capabilities,
    get_broker_provider,
    get_current_user_id,
    get_market_quote_provider,
)
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import (
    ORDER_APPROVAL_TRANSITIONS,
    ORDER_PROPOSAL_TRANSITIONS,
    OrderApprovalStatus,
    OrderProposalStatus,
)
from tradingos_api.models.execution import Account
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    ApprovalInvalidation,
    OrderApproval,
    OrderPolicyEvaluation,
    OrderProposal,
    OrderProposalVersion,
)
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.order_authority import (
    AutoPolicyGrant,
    OrderAuthorityDenied,
    assert_order_authorized,
)
from tradingos_api.policy.order_authority import OrderAuthorityMode as PolicyOrderAuthorityMode
from tradingos_api.policy.order_authority import OrderConfirmation as PolicyOrderConfirmation
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.providers.broker_capability import BrokerCapabilities
from tradingos_api.providers.quotes_bars import MarketQuoteProvider
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.order_authority import (
    ApprovalBoundFieldsResponse,
    BrokerSubmissionAttemptResponse,
    OrderApprovalCreateRequest,
    OrderApprovalDecisionRequest,
    OrderApprovalInvalidateRequest,
    OrderApprovalResponse,
    OrderPolicyEvaluationRequest,
    OrderPolicyEvaluationResponse,
    OrderProposalCreateRequest,
    OrderProposalResponse,
    OrderProposalVersionResponse,
    OrderSubmitRequest,
    OrderSubmitResponse,
    PreSubmissionSnapshotResponse,
)
from tradingos_api.services.bracket_execution import (
    BRACKET_EMULATION_DISCLOSURE,
    BracketEmulationNotAcknowledged,
    submit_bracket_order,
)
from tradingos_api.services.lifecycle import InvalidTransitionError, assert_transition_allowed
from tradingos_api.services.order_authority import (
    BoundFieldsSnapshot,
    assert_can_transition_to_approved,
    compute_bound_fields_hash,
    is_kill_switch_active,
)
from tradingos_api.services.order_execution import refresh_and_recalculate
from tradingos_api.services.paper_auto_policy import get_active_auto_policy, to_auto_policy_grant

proposals_router = APIRouter(prefix="/api/v1/order-proposals", tags=["order-proposals"])
approvals_router = APIRouter(prefix="/api/v1/order-approvals", tags=["order-approvals"])


def _proposal_response(db: Session, proposal: OrderProposal) -> OrderProposalResponse:
    inst = db.get(Instrument, proposal.instrument_id)
    assert inst is not None
    latest_version = db.scalar(
        select(OrderProposalVersion)
        .where(OrderProposalVersion.order_proposal_id == proposal.id)
        .order_by(OrderProposalVersion.version_number.desc())
    )
    assert latest_version is not None
    return OrderProposalResponse(
        id=proposal.id,
        recommendation_version_id=proposal.recommendation_version_id,
        account_id=proposal.account_id,
        instrument=InstrumentResponse.model_validate(inst),
        mode=proposal.mode,
        side=proposal.side,
        status=proposal.status,
        latest_version=OrderProposalVersionResponse.model_validate(latest_version),
    )


def _approval_response(db: Session, approval: OrderApproval) -> OrderApprovalResponse:
    bound_fields = db.scalar(
        select(ApprovalBoundFields).where(ApprovalBoundFields.order_approval_id == approval.id)
    )
    assert bound_fields is not None
    return OrderApprovalResponse(
        id=approval.id,
        order_proposal_version_id=approval.order_proposal_version_id,
        approved_by=approval.approved_by,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
        status=approval.status,
        integrity_hash=approval.integrity_hash,
        bound_fields=ApprovalBoundFieldsResponse.model_validate(bound_fields),
    )


@proposals_router.post("", response_model=OrderProposalResponse, status_code=201)
def create_order_proposal(
    payload: OrderProposalCreateRequest, db: Session = Depends(get_db)
) -> OrderProposalResponse:
    """Creates a `DRAFT` proposal from a recommendation version — the
    upstream, pre-authorization step. No policy check happens here; call
    `POST /{id}/policy-evaluation` next."""
    if payload.idempotency_key:
        existing = db.scalar(
            select(OrderProposal).where(OrderProposal.idempotency_key == payload.idempotency_key)
        )
        if existing is not None:
            return _proposal_response(db, existing)

    version = db.get(RecommendationVersion, payload.recommendation_version_id)
    if version is None:
        raise HTTPException(status_code=422, detail="Unknown recommendation_version_id.")
    recommendation = db.get(Recommendation, version.recommendation_id)
    assert recommendation is not None
    if db.get(Account, payload.account_id) is None:
        raise HTTPException(status_code=422, detail="Unknown account_id.")

    proposal = OrderProposal(
        recommendation_version_id=payload.recommendation_version_id,
        account_id=payload.account_id,
        instrument_id=recommendation.instrument_id,
        mode=recommendation.mode,
        side=payload.side,
        status=OrderProposalStatus.DRAFT,
        idempotency_key=payload.idempotency_key,
    )
    db.add(proposal)
    db.flush()
    db.add(
        OrderProposalVersion(
            order_proposal_id=proposal.id,
            version_number=1,
            order_type=payload.order_type,
            quantity=payload.quantity,
            limit_price=payload.limit_price,
            stop_price=payload.stop_price,
            time_in_force=payload.time_in_force,
            max_notional=payload.max_notional,
            rationale=payload.rationale,
        )
    )
    db.commit()
    db.refresh(proposal)
    return _proposal_response(db, proposal)


@proposals_router.get("/{proposal_id}", response_model=OrderProposalResponse)
def get_order_proposal(
    proposal_id: uuid.UUID, db: Session = Depends(get_db)
) -> OrderProposalResponse:
    proposal = db.get(OrderProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Order proposal not found.")
    return _proposal_response(db, proposal)


@proposals_router.post(
    "/{proposal_id}/policy-evaluation", response_model=OrderPolicyEvaluationResponse
)
def evaluate_order_proposal_policy(
    proposal_id: uuid.UUID,
    payload: OrderPolicyEvaluationRequest,
    db: Session = Depends(get_db),
) -> OrderPolicyEvaluationResponse:
    """Runs `policy.order_authority.assert_order_authorized()` (R0) for
    this proposal's latest version and records the outcome, win or lose,
    as an append-only `OrderPolicyEvaluation` row — then advances the
    proposal `DRAFT -> UNDER_EVALUATION -> EVALUATED`. A denial is still
    a completed evaluation (`authorized=False`), not a request error."""
    proposal = db.get(OrderProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Order proposal not found.")
    latest_version = db.scalar(
        select(OrderProposalVersion)
        .where(OrderProposalVersion.order_proposal_id == proposal.id)
        .order_by(OrderProposalVersion.version_number.desc())
    )
    assert latest_version is not None

    try:
        assert_transition_allowed(
            "OrderProposal",
            proposal.status,
            OrderProposalStatus.UNDER_EVALUATION.value,
            ORDER_PROPOSAL_TRANSITIONS,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    policy_mode = PolicyOrderAuthorityMode(payload.requested_mode.value)
    confirmation = (
        PolicyOrderConfirmation(
            confirmed_at=payload.confirmation.confirmed_at,
            account_id=payload.confirmation.account_id,
            environment=payload.confirmation.environment,
            broker_endpoint=payload.confirmation.broker_endpoint,
        )
        if payload.confirmation
        else None
    )
    auto_policy = (
        AutoPolicyGrant(
            policy_version=payload.auto_policy.policy_version,
            enabled=payload.auto_policy.enabled,
        )
        if payload.auto_policy
        else None
    )

    now = datetime.now(UTC)
    denial_reason: str | None = None
    try:
        assert_order_authorized(
            policy_mode,
            is_live=payload.is_live,
            confirmation=confirmation,
            auto_policy=auto_policy,
            now=now,
        )
        authorized = True
    except OrderAuthorityDenied as exc:
        authorized = False
        denial_reason = str(exc)

    evaluation = OrderPolicyEvaluation(
        order_proposal_version_id=latest_version.id,
        evaluated_at=now,
        requested_mode=payload.requested_mode,
        authorized=authorized,
        denial_reason=denial_reason,
    )
    db.add(evaluation)
    proposal.status = OrderProposalStatus.UNDER_EVALUATION
    proposal.status = OrderProposalStatus.EVALUATED
    db.commit()
    db.refresh(evaluation)
    return OrderPolicyEvaluationResponse.model_validate(evaluation)


@approvals_router.post("", response_model=OrderApprovalResponse, status_code=201)
def create_order_approval(
    payload: OrderApprovalCreateRequest,
    db: Session = Depends(get_db),
    quote_provider: MarketQuoteProvider = Depends(get_market_quote_provider),
) -> OrderApprovalResponse:
    """Binds an immutable `ApprovalBoundFields` snapshot to a new,
    `PENDING` approval (ADR-048) — only from a proposal version whose
    proposal has reached `EVALUATED` and whose most recent policy
    evaluation was `authorized=True`. Also snapshots the **current**
    quote into `quote_price_at_approval` (Revision Prompt 10) — the
    reference point `services/order_execution.py::refresh_and_recalculate()`
    later compares a fresh quote against, immediately before submission,
    to decide whether the market has moved enough to require a new
    approval."""
    version = db.get(OrderProposalVersion, payload.order_proposal_version_id)
    if version is None:
        raise HTTPException(status_code=422, detail="Unknown order_proposal_version_id.")
    proposal = db.get(OrderProposal, version.order_proposal_id)
    assert proposal is not None
    if proposal.status != OrderProposalStatus.EVALUATED:
        raise HTTPException(
            status_code=400,
            detail=(
                "Proposal must be EVALUATED before an approval can be created "
                f"(is {proposal.status})."
            ),
        )
    latest_evaluation = db.scalar(
        select(OrderPolicyEvaluation)
        .where(OrderPolicyEvaluation.order_proposal_version_id == version.id)
        .order_by(OrderPolicyEvaluation.evaluated_at.desc())
    )
    if latest_evaluation is None or not latest_evaluation.authorized:
        raise HTTPException(
            status_code=400,
            detail="No authorized policy evaluation exists for this proposal version.",
        )

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=payload.expires_in_seconds)
    bound_fields_input = BoundFieldsSnapshot(
        account_id=proposal.account_id,
        instrument_id=proposal.instrument_id,
        side=proposal.side.value if hasattr(proposal.side, "value") else proposal.side,
        quantity=version.quantity,
        order_type=version.order_type.value
        if hasattr(version.order_type, "value")
        else version.order_type,
        limit_price=version.limit_price,
        stop_price=version.stop_price,
        time_in_force=(
            version.time_in_force.value
            if hasattr(version.time_in_force, "value")
            else version.time_in_force
        ),
        outside_hours=payload.outside_hours,
        attached_legs=payload.attached_legs,
        max_notional=version.max_notional,
        recommendation_version_id=proposal.recommendation_version_id,
    )
    integrity_hash = compute_bound_fields_hash(bound_fields_input)

    instrument = db.get(Instrument, proposal.instrument_id)
    assert instrument is not None
    quote = quote_provider.get_latest_quote(instrument.ticker)
    quote_price_at_approval = Decimal(quote.price) if quote is not None else None

    approval = OrderApproval(
        order_proposal_version_id=version.id,
        approved_by=payload.approved_by,
        requested_at=now,
        expires_at=expires_at,
        status=OrderApprovalStatus.PENDING,
        integrity_hash=integrity_hash,
    )
    db.add(approval)
    db.flush()
    db.add(
        ApprovalBoundFields(
            order_approval_id=approval.id,
            account_id=proposal.account_id,
            instrument_id=proposal.instrument_id,
            side=proposal.side,
            quantity=version.quantity,
            order_type=version.order_type,
            limit_price=version.limit_price,
            stop_price=version.stop_price,
            time_in_force=version.time_in_force,
            outside_hours=payload.outside_hours,
            attached_legs=payload.attached_legs,
            max_notional=version.max_notional,
            recommendation_version_id=proposal.recommendation_version_id,
            quote_price_at_approval=quote_price_at_approval,
        )
    )
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@approvals_router.get("/{approval_id}", response_model=OrderApprovalResponse)
def get_order_approval(
    approval_id: uuid.UUID, db: Session = Depends(get_db)
) -> OrderApprovalResponse:
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    return _approval_response(db, approval)


@approvals_router.post("/{approval_id}/approve", response_model=OrderApprovalResponse)
def approve_order_approval(
    approval_id: uuid.UUID,
    payload: OrderApprovalDecisionRequest,
    db: Session = Depends(get_db),
) -> OrderApprovalResponse:
    """`assert_can_transition_to_approved()` (services/order_authority.py)
    is the combined guard: a legal-transition check plus a wall-clock
    expiry check, so an approval whose `expires_at` has already passed
    can never reach `APPROVED` even if nothing has marked it `EXPIRED`
    yet (R3's required test)."""
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    try:
        assert_can_transition_to_approved(approval.status, approval.expires_at)
    except (InvalidTransitionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    approval.status = OrderApprovalStatus.APPROVED
    approval.decided_at = datetime.now(UTC)
    if payload.approved_by:
        approval.approved_by = payload.approved_by
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@approvals_router.post("/{approval_id}/reject", response_model=OrderApprovalResponse)
def reject_order_approval(
    approval_id: uuid.UUID, db: Session = Depends(get_db)
) -> OrderApprovalResponse:
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    try:
        assert_transition_allowed(
            "OrderApproval",
            approval.status,
            OrderApprovalStatus.REJECTED.value,
            ORDER_APPROVAL_TRANSITIONS,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    approval.status = OrderApprovalStatus.REJECTED
    approval.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@approvals_router.post("/{approval_id}/expire", response_model=OrderApprovalResponse)
def expire_order_approval(
    approval_id: uuid.UUID, db: Session = Depends(get_db)
) -> OrderApprovalResponse:
    """Administrative/sweep endpoint — legal from `PENDING` regardless of
    whether `expires_at` has actually passed yet, mirroring the fact that
    the transition map (not the wall clock alone) is the source of truth
    for what counts as expired once recorded."""
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    try:
        assert_transition_allowed(
            "OrderApproval",
            approval.status,
            OrderApprovalStatus.EXPIRED.value,
            ORDER_APPROVAL_TRANSITIONS,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    approval.status = OrderApprovalStatus.EXPIRED
    approval.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@approvals_router.post("/{approval_id}/invalidate", response_model=OrderApprovalResponse)
def invalidate_order_approval(
    approval_id: uuid.UUID,
    payload: OrderApprovalInvalidateRequest,
    db: Session = Depends(get_db),
) -> OrderApprovalResponse:
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    try:
        assert_transition_allowed(
            "OrderApproval",
            approval.status,
            OrderApprovalStatus.INVALIDATED.value,
            ORDER_APPROVAL_TRANSITIONS,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    approval.status = OrderApprovalStatus.INVALIDATED
    approval.decided_at = datetime.now(UTC)
    db.add(
        ApprovalInvalidation(
            order_approval_id=approval.id,
            reason=payload.reason,
            detail=payload.detail,
            invalidated_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@approvals_router.get("/{approval_id}/refresh", response_model=PreSubmissionSnapshotResponse)
def refresh_order_approval(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    quote_provider: MarketQuoteProvider = Depends(get_market_quote_provider),
) -> PreSubmissionSnapshotResponse:
    """ORDER FLOW steps 2-4 as a standalone preview — "immediately
    before approval [and again immediately before submission], refresh
    quote, buying power, positions, open orders, market session, event
    timing, and risk... recalculate the proposal and show any changes."
    Never mutates anything; a client calls this to render the confirm
    screen, then separately calls `/submit` to actually act."""
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    bound_fields = db.scalar(
        select(ApprovalBoundFields).where(ApprovalBoundFields.order_approval_id == approval.id)
    )
    assert bound_fields is not None
    account = db.get(Account, bound_fields.account_id)
    instrument = db.get(Instrument, bound_fields.instrument_id)
    assert account is not None and instrument is not None

    snapshot = refresh_and_recalculate(
        db,
        account=account,
        instrument=instrument,
        quote_provider=quote_provider,
        kill_switch_active=is_kill_switch_active(db),
        price_at_approval=bound_fields.quote_price_at_approval,
        now=datetime.now(UTC),
    )
    return PreSubmissionSnapshotResponse(
        quote_price=snapshot.quote_price,
        quote_observed_at=snapshot.quote_observed_at,
        buying_power=snapshot.buying_power,
        open_position_quantity=snapshot.open_position_quantity,
        open_order_count=snapshot.open_order_count,
        is_trading_day=snapshot.trading_day.is_trading_day,
        market_closed_reason=snapshot.trading_day.skip_reason,
        upcoming_earnings_report_date=snapshot.upcoming_earnings_report_date,
        requires_reapproval=snapshot.requires_reapproval,
        reason=snapshot.reason,
    )


@approvals_router.post("/{approval_id}/submit", response_model=OrderSubmitResponse)
def submit_order_approval(
    approval_id: uuid.UUID,
    payload: OrderSubmitRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
    broker: PaperBrokerProvider = Depends(get_broker_provider),
    capabilities: BrokerCapabilities = Depends(get_broker_capabilities),
    quote_provider: MarketQuoteProvider = Depends(get_market_quote_provider),
) -> OrderSubmitResponse:
    """ORDER FLOW step 7 — the only HTTP route that reaches a broker.
    Never live: `services/order_execution.py::submit_paper_order()`
    hardcodes `is_live=False`, and `assert_broker_boundary_is_paper()`
    independently fails closed on the account type, environment label,
    and broker base URL before any broker call happens."""
    approval = db.get(OrderApproval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Order approval not found.")
    bound_fields = db.scalar(
        select(ApprovalBoundFields).where(ApprovalBoundFields.order_approval_id == approval.id)
    )
    assert bound_fields is not None
    account = db.get(Account, bound_fields.account_id)
    instrument = db.get(Instrument, bound_fields.instrument_id)
    assert account is not None and instrument is not None

    confirmation = (
        PolicyOrderConfirmation(
            confirmed_at=payload.confirmation.confirmed_at,
            account_id=payload.confirmation.account_id,
            environment=payload.confirmation.environment,
            broker_endpoint=payload.confirmation.broker_endpoint,
        )
        if payload.confirmation
        else None
    )
    policy_mode = PolicyOrderAuthorityMode(payload.requested_mode.value)
    auto_policy_grant: AutoPolicyGrant | None = None
    if policy_mode == PolicyOrderAuthorityMode.PAPER_AUTO_POLICY:
        active_policy = get_active_auto_policy(db, owner_user_id=owner_user_id)
        if active_policy is not None:
            auto_policy_grant = to_auto_policy_grant(active_policy)
            approval.auto_policy_version_id = active_policy.id

    take_profit_price = bound_fields.attached_legs.get("take_profit_price")
    stop_loss_price = bound_fields.attached_legs.get("stop_loss_price")

    try:
        result = submit_bracket_order(
            db,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=policy_mode,
            confirmation=confirmation,
            auto_policy=auto_policy_grant,
            broker=broker,
            capabilities=capabilities,
            broker_base_url=get_settings().alpaca_base_url,
            quote_provider=quote_provider,
            kill_switch_active=is_kill_switch_active(db),
            lane=payload.lane,
            source_recommendation_version_id=payload.source_recommendation_version_id,
            take_profit_price=Decimal(take_profit_price) if take_profit_price else None,
            stop_loss_price=Decimal(stop_loss_price) if stop_loss_price else None,
            emulation_acknowledged=payload.emulation_acknowledged,
        )
    except OrderAuthorityDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except BracketEmulationNotAcknowledged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    db.refresh(result.primary.attempt)
    order = result.primary.order
    return OrderSubmitResponse(
        attempt=BrokerSubmissionAttemptResponse.model_validate(result.primary.attempt),
        order_id=order.id if order is not None else None,
        order_status=order.status if order is not None else None,
        invalidated=result.primary.invalidated,
        invalidation_reason=result.primary.invalidation_reason,
        used_native_bracket=result.used_native_bracket,
        disclosure=BRACKET_EMULATION_DISCLOSURE if result.disclosure_shown else None,
        stop_loss_order_id=result.stop_loss_order_id,
        take_profit_order_id=result.take_profit_order_id,
    )
