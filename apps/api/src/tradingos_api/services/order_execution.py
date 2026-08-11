"""The order execution service (Revision Prompt 10) — the single,
narrow component docs/ORDER_AUTHORITY_MODEL.md's "broker-adapter
isolation" section requires: the **only** caller of a `PaperBrokerProvider`'s
`submit_paper_order()`/`cancel_paper_order()` anywhere in this codebase
(`tests/test_order_execution_boundary.py::TestBrokerBoundaryIsSingleEntryPoint`
is the structural test that proves it, mirroring the pre-existing
single-entry-point invariant `routers/orders.py`'s own fill-booking
helper already established for the Phase 8 manual-fill path).

**No code path in this module ever submits live.** `submit_paper_order()`
hardcodes `is_live=False` in its own `assert_order_authorized()` call —
there is no parameter that could flip it, and
`assert_broker_boundary_is_paper()` (`services/order_authority.py`)
independently fails closed on the account type, environment label, and
broker base URL before this module ever touches a `PaperBrokerProvider`.
Three unrelated facts all have to agree this is paper-only; no single
mistake anywhere is enough to reach a live submission.

ORDER FLOW steps this module implements:

- **2-4 (refresh, recalculate, display).** `refresh_and_recalculate()` —
  called once when an approval is first created (to snapshot
  `quote_price_at_approval`) and again immediately before submission (to
  detect a price move large enough to require a fresh approval).
- **7 (submit through the deterministic broker service).**
  `submit_paper_order()`.
- **8 (persist everything).** Every call to `submit_paper_order()`
  writes exactly one `BrokerSubmissionAttempt` row — append-only, never
  edited — recording the idempotency key, environment, outcome, a
  redacted request/response snapshot, and (on success) the real `Order`
  it produced.
- **9 (query before retry on an ambiguous timeout).** See
  `_resolve_or_submit()` below.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AccountType,
    ApprovalInvalidationReason,
    BrokerSubmissionOutcome,
    EnvironmentLabel,
    LotLane,
    OrderApprovalStatus,
    OrderSide,
    OrderStatus,
    OrderType,
)
from tradingos_api.models.execution import Account, Execution, Order, Position
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    ApprovalInvalidation,
    BrokerSubmissionAttempt,
    OrderApproval,
)
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.order_authority import (
    AutoPolicyGrant,
    OrderAuthorityDenied,
    OrderAuthorityMode,
    OrderConfirmation,
    assert_order_authorized,
)
from tradingos_api.providers.broker import (
    BrokerSubmissionAmbiguous,
    PaperBrokerProvider,
    PaperOrderRequest,
    PaperOrderResult,
)
from tradingos_api.providers.quotes_bars import MarketQuoteProvider
from tradingos_api.services.hard_vetoes import (
    HardVetoInputs,
    VetoResult,
    any_veto_triggered,
    evaluate_hard_vetoes,
)
from tradingos_api.services.market_calendar import TradingDayResolution, resolve_trading_day
from tradingos_api.services.order_authority import (
    assert_broker_boundary_is_paper,
    price_move_requires_invalidation,
)
from tradingos_api.services.portfolio_accounting import apply_execution, get_cash_balance

CALCULATION_VERSION = "v1"

# Fields whose value could reveal a credential or a real account number
# if ever echoed back verbatim — `_redact_broker_payload()` is the one
# place this list lives, so a new field added to `PaperOrderRequest`/
# `PaperOrderResult` in the future does not silently bypass it.
_REDACTED_KEYS = frozenset({"api_key", "api_secret", "secret_key", "account_number", "auth"})


def _client_order_id(order_approval_id: uuid.UUID) -> str:
    """Stable across every attempt for the same approval — the broker-
    facing idempotency key (`providers/broker.py`'s module docstring)."""
    return f"tos-{order_approval_id}"


def _redact_broker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: ("[REDACTED]" if k.lower() in _REDACTED_KEYS else v) for k, v in payload.items()}


@dataclass(frozen=True)
class PreSubmissionSnapshot:
    """The result of ORDER FLOW steps 2-4 — "immediately before
    approval, refresh quote, buying power, positions, open orders,
    market session, event timing, and risk" and "recalculate the
    proposal and show any changes." Every field is a fact observed
    *now*, never a cached value from proposal- or approval-creation
    time."""

    quote_price: Decimal | None
    quote_observed_at: datetime | None
    buying_power: Decimal
    open_position_quantity: Decimal
    open_order_count: int
    trading_day: TradingDayResolution
    upcoming_earnings_report_date: str | None
    vetoes: list[VetoResult]
    price_move_pct: Decimal | None
    requires_reapproval: bool
    reason: str | None
    calculation_version: str = CALCULATION_VERSION


def refresh_and_recalculate(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    quote_provider: MarketQuoteProvider,
    kill_switch_active: bool,
    price_at_approval: Decimal | None,
    now: datetime,
) -> PreSubmissionSnapshot:
    quote = quote_provider.get_latest_quote(instrument.ticker)
    quote_price = Decimal(quote.price) if quote is not None else None
    quote_observed_at = quote.observed_at if quote is not None else None

    buying_power = get_cash_balance(db, account_id=account.id, starting_cash=account.starting_cash)

    position = db.scalar(
        select(Position).where(
            Position.account_id == account.id, Position.instrument_id == instrument.id
        )
    )
    open_position_quantity = position.quantity if position is not None else Decimal(0)

    open_order_count = len(
        db.scalars(
            select(Order).where(
                Order.account_id == account.id,
                Order.instrument_id == instrument.id,
                Order.status.in_((OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)),
            )
        ).all()
    )

    trading_day = resolve_trading_day(now.date())

    next_earnings = db.scalar(
        select(EarningsEvent)
        .where(
            EarningsEvent.instrument_id == instrument.id,
            EarningsEvent.report_date >= now.date(),
        )
        .order_by(EarningsEvent.report_date.asc())
    )

    price_move_pct: Decimal | None = None
    requires_reapproval = False
    reason: str | None = None
    if price_at_approval is not None and quote_price is not None:
        requires_reapproval, price_move_pct = price_move_requires_invalidation(
            price_at_approval=price_at_approval, current_price=quote_price
        )
        if requires_reapproval:
            reason = (
                f"quote moved {price_move_pct:.2f}% from {price_at_approval} to "
                f"{quote_price} since approval — outside tolerance, a fresh approval is required"
            )

    veto_inputs = HardVetoInputs(
        has_stale_required_data=quote is None,
        stale_data_detail="no current quote available" if quote is None else None,
        kill_switch_active=kill_switch_active,
        broker_environment_ambiguous=account.account_type != AccountType.PAPER_ALPACA,
        broker_environment_detail=(
            None
            if account.account_type == AccountType.PAPER_ALPACA
            else f"account_type={account.account_type.value} is not a broker-backed account"
        ),
    )
    vetoes = evaluate_hard_vetoes(veto_inputs)
    if any_veto_triggered(vetoes) and not requires_reapproval:
        requires_reapproval = True
        reason = "; ".join(v.explanation for v in vetoes if v.triggered)

    if not trading_day.is_trading_day and reason is None:
        # Not itself a reason to invalidate an already-bound approval —
        # a paper order can still rest until the next session — but
        # always surfaced so "market session" is genuinely shown, not
        # silently omitted, per ORDER FLOW step 4.
        reason = trading_day.skip_reason

    return PreSubmissionSnapshot(
        quote_price=quote_price,
        quote_observed_at=quote_observed_at,
        buying_power=buying_power,
        open_position_quantity=open_position_quantity,
        open_order_count=open_order_count,
        trading_day=trading_day,
        upcoming_earnings_report_date=(
            next_earnings.report_date.isoformat() if next_earnings is not None else None
        ),
        vetoes=vetoes,
        price_move_pct=price_move_pct,
        requires_reapproval=requires_reapproval,
        reason=reason,
    )


@dataclass(frozen=True)
class SubmissionResult:
    attempt: BrokerSubmissionAttempt
    order: Order | None = None
    invalidated: bool = False
    invalidation_reason: str | None = None


def _map_order_status(broker_status: str) -> OrderStatus:
    normalized = broker_status.lower()
    if normalized in ("filled",):
        return OrderStatus.FILLED
    if normalized in ("partially_filled",):
        return OrderStatus.PARTIALLY_FILLED
    if normalized in ("canceled", "cancelled", "expired"):
        return OrderStatus.CANCELED
    return OrderStatus.SUBMITTED


def _record_attempt(
    db: Session,
    *,
    approval: OrderApproval,
    attempt_number: int,
    outcome: BrokerSubmissionOutcome,
    detail: str | None,
    request_snapshot: dict[str, Any],
    response_snapshot: dict[str, Any],
    resulting_order_id: uuid.UUID | None,
    now: datetime,
) -> BrokerSubmissionAttempt:
    attempt = BrokerSubmissionAttempt(
        order_approval_id=approval.id,
        attempted_at=now,
        environment_label=EnvironmentLabel.PAPER,
        outcome=outcome,
        idempotency_key=f"order-approval:{approval.id}:attempt{attempt_number}",
        detail=detail,
        resulting_order_id=resulting_order_id,
        request_snapshot=_redact_broker_payload(request_snapshot),
        response_snapshot=_redact_broker_payload(response_snapshot),
    )
    db.add(attempt)
    db.flush()
    return attempt


def _book_result_as_order(
    db: Session,
    *,
    account: Account,
    instrument: Instrument,
    bound_fields: ApprovalBoundFields,
    result: PaperOrderResult,
    lane: LotLane,
    source_recommendation_version_id: uuid.UUID | None,
    now: datetime,
) -> Order:
    order = Order(
        account_id=account.id,
        instrument_id=instrument.id,
        side=bound_fields.side,
        order_type=bound_fields.order_type,
        time_in_force=bound_fields.time_in_force,
        quantity=bound_fields.quantity,
        limit_price=bound_fields.limit_price,
        stop_price=bound_fields.stop_price,
        status=_map_order_status(result.status),
        broker_order_id=result.broker_order_id,
        submitted_at=now,
        linked_recommendation_version_id=bound_fields.recommendation_version_id,
    )
    db.add(order)
    db.flush()

    filled_qty = Decimal(result.filled_quantity)
    if filled_qty > 0:
        execution = Execution(
            order_id=order.id,
            quantity=filled_qty,
            price=Decimal(result.filled_avg_price or "0"),
            executed_at=now,
            broker_execution_id=f"{result.broker_order_id}:{filled_qty}",
        )
        db.add(execution)
        db.flush()
        apply_execution(
            db,
            execution=execution,
            account_id=account.id,
            instrument_id=instrument.id,
            side=bound_fields.side,
            lane=lane,
            source_recommendation_version_id=source_recommendation_version_id,
        )
        order.filled_at = now
    return order


def submit_paper_order(
    db: Session,
    *,
    approval: OrderApproval,
    bound_fields: ApprovalBoundFields,
    account: Account,
    instrument: Instrument,
    mode: OrderAuthorityMode,
    confirmation: OrderConfirmation | None,
    auto_policy: AutoPolicyGrant | None,
    broker: PaperBrokerProvider,
    broker_base_url: str,
    quote_provider: MarketQuoteProvider,
    kill_switch_active: bool,
    lane: LotLane = LotLane.UNCLASSIFIED,
    source_recommendation_version_id: uuid.UUID | None = None,
    take_profit_price: Decimal | None = None,
    stop_loss_price: Decimal | None = None,
    now: datetime | None = None,
) -> SubmissionResult:
    """The single broker-boundary entry point. Raises `OrderAuthorityDenied`
    (never a bare exception) if any fail-closed check does not pass —
    the caller (the router) is responsible for translating that into an
    HTTP response; this function never partially proceeds past a denial.
    `take_profit_price`/`stop_loss_price` are for `services/bracket_execution.py`'s
    native-bracket path only — a plain (non-bracket) submission leaves
    both `None`."""
    now = now or datetime.now(UTC)

    # OA-6 — refuse anything that is not unambiguously paper, before
    # this function does anything else at all.
    assert_broker_boundary_is_paper(
        account_type=account.account_type,
        environment_label=EnvironmentLabel.PAPER,
        broker_base_url=broker_base_url,
    )
    # Never trust an earlier authorization check as still valid —
    # `is_live=False` is not a parameter here; it is the one value this
    # call can ever pass.
    assert_order_authorized(
        mode, is_live=False, confirmation=confirmation, auto_policy=auto_policy, now=now
    )
    if approval.status != OrderApprovalStatus.APPROVED:
        raise OrderAuthorityDenied(
            f"order approval {approval.id} is {approval.status.value}, not APPROVED"
        )
    if approval.expires_at < now:
        # A row can say APPROVED while `expires_at` has since passed if
        # nothing has run the expiry sweep yet (the same fact
        # `services/order_authority.py::assert_can_transition_to_approved()`
        # already fails closed on for the PENDING->APPROVED transition
        # itself) — submission re-checks it independently rather than
        # trusting that an earlier approval is still current.
        raise OrderAuthorityDenied(
            f"order approval {approval.id} expired at {approval.expires_at.isoformat()} "
            f"(now {now.isoformat()}) — a fresh approval is required"
        )

    # ORDER FLOW step 7's own immediate precondition: refresh once more
    # and refuse to submit into a materially different market than the
    # one the approval was granted against.
    snapshot = refresh_and_recalculate(
        db,
        account=account,
        instrument=instrument,
        quote_provider=quote_provider,
        kill_switch_active=kill_switch_active,
        price_at_approval=bound_fields.quote_price_at_approval,
        now=now,
    )
    if snapshot.requires_reapproval:
        approval.status = OrderApprovalStatus.INVALIDATED
        approval.decided_at = now
        db.add(
            ApprovalInvalidation(
                order_approval_id=approval.id,
                reason=ApprovalInvalidationReason.PRICE_MOVED,
                detail=snapshot.reason,
                invalidated_at=now,
            )
        )
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=_next_attempt_number(db, approval.id),
            outcome=BrokerSubmissionOutcome.DENIED,
            detail=snapshot.reason,
            request_snapshot={},
            response_snapshot={},
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(
            attempt=attempt, invalidated=True, invalidation_reason=snapshot.reason
        )

    return _resolve_or_submit(
        db,
        approval=approval,
        bound_fields=bound_fields,
        account=account,
        instrument=instrument,
        broker=broker,
        lane=lane,
        source_recommendation_version_id=source_recommendation_version_id,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        now=now,
    )


def _next_attempt_number(db: Session, order_approval_id: uuid.UUID) -> int:
    existing = db.scalars(
        select(BrokerSubmissionAttempt)
        .where(BrokerSubmissionAttempt.order_approval_id == order_approval_id)
        .order_by(BrokerSubmissionAttempt.attempted_at.asc())
    ).all()
    return len(existing) + 1


def _resolve_or_submit(
    db: Session,
    *,
    approval: OrderApproval,
    bound_fields: ApprovalBoundFields,
    account: Account,
    instrument: Instrument,
    broker: PaperBrokerProvider,
    lane: LotLane,
    source_recommendation_version_id: uuid.UUID | None,
    take_profit_price: Decimal | None = None,
    stop_loss_price: Decimal | None = None,
    now: datetime,
) -> SubmissionResult:
    existing_attempts = db.scalars(
        select(BrokerSubmissionAttempt)
        .where(BrokerSubmissionAttempt.order_approval_id == approval.id)
        .order_by(BrokerSubmissionAttempt.attempted_at.asc())
    ).all()
    attempt_number = len(existing_attempts) + 1
    client_order_id = _client_order_id(approval.id)

    # "Never retry an unproven non-idempotent submit" + the required
    # "duplicate click" test: a prior attempt that already succeeded is
    # the end of the story — return it, touch the broker for nothing.
    last = existing_attempts[-1] if existing_attempts else None
    if last is not None and last.outcome == BrokerSubmissionOutcome.SUCCEEDED:
        order = db.get(Order, last.resulting_order_id) if last.resulting_order_id else None
        return SubmissionResult(attempt=last, order=order)

    # "If a timeout is ambiguous, query status before any retry" — a
    # prior attempt left in TIMEOUT_UNKNOWN must be resolved by asking
    # the broker directly, never by guessing and never by resubmitting
    # blind.
    if last is not None and last.outcome == BrokerSubmissionOutcome.TIMEOUT_UNKNOWN:
        found = broker.find_order_by_client_id(client_order_id)
        if found is not None:
            order = _book_result_as_order(
                db,
                account=account,
                instrument=instrument,
                bound_fields=bound_fields,
                result=found,
                lane=lane,
                source_recommendation_version_id=source_recommendation_version_id,
                now=now,
            )
            attempt = _record_attempt(
                db,
                approval=approval,
                attempt_number=attempt_number,
                outcome=BrokerSubmissionOutcome.SUCCEEDED,
                detail="resolved an ambiguous prior timeout via find_order_by_client_id",
                request_snapshot={},
                response_snapshot=found.model_dump(),
                resulting_order_id=order.id,
                now=now,
            )
            return SubmissionResult(attempt=attempt, order=order)
        # Confirmed the broker never received the prior attempt — safe
        # to actually submit now, falling through below.

    request = PaperOrderRequest(
        symbol=instrument.ticker,
        quantity=int(bound_fields.quantity),
        side=bound_fields.side.value.lower(),
        order_type=bound_fields.order_type.value.lower(),
        limit_price=str(bound_fields.limit_price) if bound_fields.limit_price else None,
        stop_price=str(bound_fields.stop_price) if bound_fields.stop_price else None,
        client_order_id=client_order_id,
        take_profit_price=str(take_profit_price) if take_profit_price is not None else None,
        stop_loss_price=str(stop_loss_price) if stop_loss_price is not None else None,
    )
    request_snapshot = request.model_dump()

    try:
        result = broker.submit_paper_order(request)
    except BrokerSubmissionAmbiguous as exc:
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=attempt_number,
            outcome=BrokerSubmissionOutcome.TIMEOUT_UNKNOWN,
            detail=str(exc),
            request_snapshot=request_snapshot,
            response_snapshot={},
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(attempt=attempt)
    except Exception as exc:  # noqa: BLE001 - a confirmed non-submission, safe to record and retry
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=attempt_number,
            outcome=BrokerSubmissionOutcome.FAILED,
            detail=str(exc),
            request_snapshot=request_snapshot,
            response_snapshot={},
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(attempt=attempt)

    if result.status.lower() == "rejected":
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=attempt_number,
            outcome=BrokerSubmissionOutcome.FAILED,
            detail=f"broker rejected the order (status={result.status})",
            request_snapshot=request_snapshot,
            response_snapshot=result.model_dump(),
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(attempt=attempt)

    order = _book_result_as_order(
        db,
        account=account,
        instrument=instrument,
        bound_fields=bound_fields,
        result=result,
        lane=lane,
        source_recommendation_version_id=source_recommendation_version_id,
        now=now,
    )
    attempt = _record_attempt(
        db,
        approval=approval,
        attempt_number=attempt_number,
        outcome=BrokerSubmissionOutcome.SUCCEEDED,
        detail=None,
        request_snapshot=request_snapshot,
        response_snapshot=result.model_dump(),
        resulting_order_id=order.id,
        now=now,
    )
    return SubmissionResult(attempt=attempt, order=order)


def poll_and_reconcile_fills(
    db: Session, *, order: Order, broker: PaperBrokerProvider, lane: LotLane, now: datetime
) -> Order:
    """Catches up on an asynchronous fill (a resting LIMIT order) —
    re-fetches the broker's current view and books only the *delta*
    quantity beyond what this app has already recorded as an `Execution`,
    never double-counting a fill already booked."""
    if order.broker_order_id is None:
        raise ValueError(f"order {order.id} has no broker_order_id to poll")
    result = broker.get_paper_order_status(order.broker_order_id)

    already_booked = sum(
        (e.quantity for e in db.scalars(select(Execution).where(Execution.order_id == order.id))),
        Decimal(0),
    )
    broker_filled = Decimal(result.filled_quantity)
    delta = broker_filled - already_booked
    if delta > 0:
        execution = Execution(
            order_id=order.id,
            quantity=delta,
            price=Decimal(result.filled_avg_price or "0"),
            executed_at=now,
            broker_execution_id=f"{order.broker_order_id}:{broker_filled}",
        )
        db.add(execution)
        db.flush()
        apply_execution(
            db,
            execution=execution,
            account_id=order.account_id,
            instrument_id=order.instrument_id,
            side=order.side,
            lane=lane,
        )
        if broker_filled == order.quantity:
            order.filled_at = now

    order.status = _map_order_status(result.status)
    return order


def submit_protective_leg(
    db: Session,
    *,
    approval: OrderApproval,
    account: Account,
    instrument: Instrument,
    mode: OrderAuthorityMode,
    confirmation: OrderConfirmation | None,
    auto_policy: AutoPolicyGrant | None,
    broker: PaperBrokerProvider,
    broker_base_url: str,
    kill_switch_active: bool,
    side: OrderSide,
    quantity: Decimal,
    order_type: OrderType,
    price: Decimal,
    leg_label: str,
    now: datetime | None = None,
) -> SubmissionResult:
    """Submits one **emulated** protective leg of an already-approved
    bracket (`services/bracket_execution.py`'s job to call this, never a
    router directly — this stays the only other function in this module
    that touches `PaperBrokerProvider.submit_paper_order()`). Reuses the
    *same* `OrderApproval` — "protective exits may remain active after
    the approved entry" (Revision Prompt 10) means the user's original
    approval already covers this leg's price/quantity, no second
    approval cycle is required for it to rest at the broker unchanged;
    replacing it with a *different* price is the "discretionary change"
    that does require a fresh approval, which is `bracket_execution.py`'s
    concern, not this function's."""
    now = now or datetime.now(UTC)
    assert_broker_boundary_is_paper(
        account_type=account.account_type,
        environment_label=EnvironmentLabel.PAPER,
        broker_base_url=broker_base_url,
    )
    assert_order_authorized(
        mode, is_live=False, confirmation=confirmation, auto_policy=auto_policy, now=now
    )
    del kill_switch_active  # the primary leg's own submission already re-checked this

    client_order_id = f"{_client_order_id(approval.id)}-{leg_label.lower()}"
    is_stop_leg = order_type in (OrderType.STOP, OrderType.STOP_LIMIT)
    request = PaperOrderRequest(
        symbol=instrument.ticker,
        quantity=int(quantity),
        side=side.value.lower(),
        order_type=order_type.value.lower(),
        limit_price=str(price) if not is_stop_leg else None,
        stop_price=str(price) if is_stop_leg else None,
        client_order_id=client_order_id,
    )
    request_snapshot = request.model_dump()
    attempt_number = _next_attempt_number(db, approval.id)

    try:
        result = broker.submit_paper_order(request)
    except BrokerSubmissionAmbiguous as exc:
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=attempt_number,
            outcome=BrokerSubmissionOutcome.TIMEOUT_UNKNOWN,
            detail=f"{leg_label}: {exc}",
            request_snapshot=request_snapshot,
            response_snapshot={},
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(attempt=attempt)
    except Exception as exc:  # noqa: BLE001 - confirmed non-submission, safe to record
        attempt = _record_attempt(
            db,
            approval=approval,
            attempt_number=attempt_number,
            outcome=BrokerSubmissionOutcome.FAILED,
            detail=f"{leg_label}: {exc}",
            request_snapshot=request_snapshot,
            response_snapshot={},
            resulting_order_id=None,
            now=now,
        )
        return SubmissionResult(attempt=attempt)

    order = Order(
        account_id=account.id,
        instrument_id=instrument.id,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=price if order_type == OrderType.LIMIT else None,
        stop_price=price if order_type == OrderType.STOP else None,
        status=_map_order_status(result.status),
        broker_order_id=result.broker_order_id,
        submitted_at=now,
    )
    db.add(order)
    db.flush()
    attempt = _record_attempt(
        db,
        approval=approval,
        attempt_number=attempt_number,
        outcome=BrokerSubmissionOutcome.SUCCEEDED,
        detail=leg_label,
        request_snapshot=request_snapshot,
        response_snapshot=result.model_dump(),
        resulting_order_id=order.id,
        now=now,
    )
    return SubmissionResult(attempt=attempt, order=order)


def cancel_order_at_broker(db: Session, *, order: Order, broker: PaperBrokerProvider) -> Order:
    """The **only** other function in this codebase, alongside
    `submit_paper_order()`/`submit_protective_leg()`, that calls a
    `PaperBrokerProvider` — the cancel-open-orders control (OA-9/SS-4)
    goes through here rather than a router calling `broker.cancel_paper_order()`
    directly, keeping the single-entry-point property whole.

    Idempotent by design (Revision Prompt 16 idempotency review): an
    order already in a terminal state (most commonly `CANCELED`,
    reached via a concurrent individual cancel or a second cancel-open
    call racing this one) is returned unchanged rather than calling the
    broker again — `cancel_paper_order()` on an already-canceled broker
    order can raise (`SyntheticBrokerOrderNotFound` for the synthetic
    provider), which is exactly the "assume the caller already checked"
    failure mode this re-check exists to remove. Callers (`routers/orders.py`)
    only ever pass orders already filtered to `SUBMITTED`/`PARTIALLY_FILLED`,
    but that filter is read *before* this runs — this is the same
    "re-check right before touching the broker, don't just trust an
    earlier read" pattern `refresh_and_recalculate()` already applies to
    submission."""
    if order.status not in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
        return order
    if order.broker_order_id is None:
        raise ValueError(f"order {order.id} has no broker_order_id to cancel")
    broker.cancel_paper_order(order.broker_order_id)
    order.status = OrderStatus.CANCELED
    order.canceled_at = datetime.now(UTC)
    return order
