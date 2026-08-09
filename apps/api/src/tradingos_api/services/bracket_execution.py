"""Bracket/OCO order submission (Revision Prompt 10) — "prefer
broker-native bracket/OCO when supported. If unsupported, disclose the
reliability limitation before allowing emulation. Protective exits may
remain active after the approved entry. Replacing a discretionary
target or increasing risk requires a new approval."

`submit_bracket_order()` is the one place that decides native vs.
emulated and is the only caller of `services/order_execution.py`'s
bracket-aware entry points (`submit_paper_order(take_profit_price=...,
stop_loss_price=...)` for native, `submit_protective_leg()` for
emulated legs) — it never touches a `PaperBrokerProvider` itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import LotLane, OrderLegRole, OrderSide, OrderStatus, OrderType
from tradingos_api.models.execution import Account, Execution, Order, OrderLeg
from tradingos_api.models.order_authority import ApprovalBoundFields, OrderApproval
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.order_authority import (
    AutoPolicyGrant,
    OrderAuthorityMode,
    OrderConfirmation,
)
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.providers.broker_capability import BrokerCapabilities
from tradingos_api.providers.quotes_bars import MarketQuoteProvider
from tradingos_api.services.order_execution import (
    SubmissionResult,
    submit_paper_order,
    submit_protective_leg,
)

CALCULATION_VERSION = "v1"

BRACKET_EMULATION_DISCLOSURE = (
    "This broker connection does not support native bracket/OCO orders. "
    "The stop-loss and take-profit legs will be submitted as independent, "
    "separately-tracked orders sharing one bracket group, not a single "
    "broker-guaranteed unit. If the primary entry fills and this "
    "application loses connectivity or is restarted before the "
    "protective legs are submitted, the resulting position is "
    "temporarily unprotected until a follow-up review submits them "
    "manually. Each leg is also its own independent order at the broker "
    "— canceling one does not automatically cancel the other (no true "
    "OCO relationship exists at the broker), only in this application's "
    "own bookkeeping. This is a real reliability limitation of emulated "
    "brackets, not a theoretical one."
)


class BracketEmulationNotAcknowledged(RuntimeError):
    """ "If unsupported, disclose the reliability limitation before
    allowing emulation" as an enforced precondition — a caller that has
    not set `emulation_acknowledged=True` cannot reach the emulated path
    at all, regardless of UI intent."""


@dataclass(frozen=True)
class BracketSubmissionResult:
    primary: SubmissionResult
    stop_loss_order_id: uuid.UUID | None = None
    take_profit_order_id: uuid.UUID | None = None
    used_native_bracket: bool = False
    disclosure_shown: bool = False
    bracket_group_id: uuid.UUID | None = None
    calculation_version: str = CALCULATION_VERSION


def _opposite_side(side: OrderSide) -> OrderSide:
    return OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY


def _ensure_leg(
    db: Session,
    *,
    order_id: uuid.UUID,
    role: OrderLegRole,
    bracket_group_id: uuid.UUID | None = None,
) -> None:
    """`order_legs.order_id` is unique — a duplicate-click resubmit
    (`services/order_execution.py`'s own idempotent short-circuit)
    returns the *same* `Order` a second time, which must not try to
    insert a second `OrderLeg` row for it."""
    existing = db.scalar(select(OrderLeg).where(OrderLeg.order_id == order_id))
    if existing is not None:
        return
    db.add(OrderLeg(order_id=order_id, role=role, bracket_group_id=bracket_group_id))


def submit_bracket_order(
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
    capabilities: BrokerCapabilities,
    broker_base_url: str,
    quote_provider: MarketQuoteProvider,
    kill_switch_active: bool,
    lane: LotLane = LotLane.UNCLASSIFIED,
    source_recommendation_version_id: uuid.UUID | None = None,
    take_profit_price: Decimal | None = None,
    stop_loss_price: Decimal | None = None,
    emulation_acknowledged: bool = False,
    now: datetime | None = None,
) -> BracketSubmissionResult:
    now = now or datetime.now(UTC)
    is_bracket = take_profit_price is not None or stop_loss_price is not None

    if not is_bracket:
        result = submit_paper_order(
            db,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=mode,
            confirmation=confirmation,
            auto_policy=auto_policy,
            broker=broker,
            broker_base_url=broker_base_url,
            quote_provider=quote_provider,
            kill_switch_active=kill_switch_active,
            lane=lane,
            source_recommendation_version_id=source_recommendation_version_id,
            now=now,
        )
        if result.order is not None:
            _ensure_leg(db, order_id=result.order.id, role=OrderLegRole.PRIMARY)
        return BracketSubmissionResult(primary=result)

    if capabilities.supports_native_brackets:
        result = submit_paper_order(
            db,
            approval=approval,
            bound_fields=bound_fields,
            account=account,
            instrument=instrument,
            mode=mode,
            confirmation=confirmation,
            auto_policy=auto_policy,
            broker=broker,
            broker_base_url=broker_base_url,
            quote_provider=quote_provider,
            kill_switch_active=kill_switch_active,
            lane=lane,
            source_recommendation_version_id=source_recommendation_version_id,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            now=now,
        )
        bracket_group_id = uuid.uuid4() if result.order is not None else None
        if result.order is not None:
            _ensure_leg(
                db,
                order_id=result.order.id,
                role=OrderLegRole.PRIMARY,
                bracket_group_id=bracket_group_id,
            )
        return BracketSubmissionResult(
            primary=result, used_native_bracket=True, bracket_group_id=bracket_group_id
        )

    if not emulation_acknowledged:
        raise BracketEmulationNotAcknowledged(BRACKET_EMULATION_DISCLOSURE)

    primary_result = submit_paper_order(
        db,
        approval=approval,
        bound_fields=bound_fields,
        account=account,
        instrument=instrument,
        mode=mode,
        confirmation=confirmation,
        auto_policy=auto_policy,
        broker=broker,
        broker_base_url=broker_base_url,
        quote_provider=quote_provider,
        kill_switch_active=kill_switch_active,
        lane=lane,
        source_recommendation_version_id=source_recommendation_version_id,
        now=now,
    )
    bracket_group_id = uuid.uuid4()
    stop_leg_order_id: uuid.UUID | None = None
    take_leg_order_id: uuid.UUID | None = None

    if primary_result.order is not None:
        _ensure_leg(
            db,
            order_id=primary_result.order.id,
            role=OrderLegRole.PRIMARY,
            bracket_group_id=bracket_group_id,
        )
        # "Protective exits may remain active after the approved entry"
        # — a protective leg is submitted once the primary is filled
        # (nothing to protect before then); a partial fill still gets
        # protective legs sized to the filled quantity, not the full
        # order, so nothing is over-protected on an incomplete entry.
        filled_quantity = (
            primary_result.order.quantity
            if (primary_result.order.status == OrderStatus.FILLED)
            else (
                None
                if primary_result.order.status != OrderStatus.PARTIALLY_FILLED
                else _sum_filled(db, primary_result.order)
            )
        )
        if filled_quantity:
            exit_side = _opposite_side(bound_fields.side)
            if stop_loss_price is not None:
                leg_result = submit_protective_leg(
                    db,
                    approval=approval,
                    account=account,
                    instrument=instrument,
                    mode=mode,
                    confirmation=confirmation,
                    auto_policy=auto_policy,
                    broker=broker,
                    broker_base_url=broker_base_url,
                    kill_switch_active=kill_switch_active,
                    side=exit_side,
                    quantity=filled_quantity,
                    order_type=OrderType.STOP,
                    price=stop_loss_price,
                    leg_label="STOP_LOSS",
                    now=now,
                )
                if leg_result.order is not None:
                    stop_leg_order_id = leg_result.order.id
                    _ensure_leg(
                        db,
                        order_id=leg_result.order.id,
                        role=OrderLegRole.STOP_LOSS,
                        bracket_group_id=bracket_group_id,
                    )
            if take_profit_price is not None:
                leg_result = submit_protective_leg(
                    db,
                    approval=approval,
                    account=account,
                    instrument=instrument,
                    mode=mode,
                    confirmation=confirmation,
                    auto_policy=auto_policy,
                    broker=broker,
                    broker_base_url=broker_base_url,
                    kill_switch_active=kill_switch_active,
                    side=exit_side,
                    quantity=filled_quantity,
                    order_type=OrderType.LIMIT,
                    price=take_profit_price,
                    leg_label="TAKE_PROFIT",
                    now=now,
                )
                if leg_result.order is not None:
                    take_leg_order_id = leg_result.order.id
                    _ensure_leg(
                        db,
                        order_id=leg_result.order.id,
                        role=OrderLegRole.TAKE_PROFIT,
                        bracket_group_id=bracket_group_id,
                    )

    return BracketSubmissionResult(
        primary=primary_result,
        stop_loss_order_id=stop_leg_order_id,
        take_profit_order_id=take_leg_order_id,
        used_native_bracket=False,
        disclosure_shown=True,
        bracket_group_id=bracket_group_id,
    )


def _sum_filled(db: Session, order: Order) -> Decimal:
    return sum(
        (e.quantity for e in db.scalars(select(Execution).where(Execution.order_id == order.id))),
        Decimal(0),
    )
