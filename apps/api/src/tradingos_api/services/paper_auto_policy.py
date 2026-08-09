"""The `PAPER_AUTO_POLICY` eligibility engine (Revision Prompt 10, OA-4).

"Auto-policy can never override a hard risk or data-quality gate" is
enforced structurally here, not by convention: `evaluate_auto_submission()`
takes the hard-veto results as a required parameter and ANDs them with
its own policy checks — there is no code path through this module that
produces an eligible result while a hard veto is triggered, matching
this project's AND-gate philosophy used everywhere else a deterministic
gate exists (`services/hard_vetoes.py`, `services/baseline_eligibility.py`).

"Disabled by default": `get_active_auto_policy()` returns `None` both
when no `PaperAutoPolicyVersion` row has ever been written for a user
and when the latest one has `enabled=False` — identical treatment,
matching `policy.order_authority.AutoPolicyGrant(enabled=False, ...)`'s
own "an unversioned or disabled grant authorizes nothing."
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import OrderApprovalStatus, OrderStatus, StrategyFamily
from tradingos_api.models.execution import Order
from tradingos_api.models.order_authority import (
    ApprovalBoundFields,
    BrokerSubmissionAttempt,
    OrderApproval,
)
from tradingos_api.models.order_authority import (
    PaperAutoPolicyVersion as PaperAutoPolicyVersionModel,
)
from tradingos_api.policy.order_authority import AutoPolicyGrant
from tradingos_api.services.hard_vetoes import VetoResult, any_veto_triggered
from tradingos_api.services.market_calendar import DISPLAY_TIMEZONE

CALCULATION_VERSION = "v1"


def get_active_auto_policy(
    db: Session, *, owner_user_id: uuid.UUID
) -> PaperAutoPolicyVersionModel | None:
    latest = db.scalar(
        select(PaperAutoPolicyVersionModel)
        .where(PaperAutoPolicyVersionModel.owner_user_id == owner_user_id)
        .order_by(PaperAutoPolicyVersionModel.version_number.desc())
    )
    if latest is None or not latest.enabled:
        return None
    return latest


def to_auto_policy_grant(policy: PaperAutoPolicyVersionModel) -> AutoPolicyGrant:
    return AutoPolicyGrant(policy_version=str(policy.version_number), enabled=policy.enabled)


@dataclass(frozen=True)
class AutoPolicyEvaluation:
    eligible: bool
    failed_conditions: list[str] = field(default_factory=list)
    calculation_version: str = CALCULATION_VERSION


def _within_allowed_time_window(windows: list[dict[str, object]], now_local_time: time) -> bool:
    if not windows:
        return False
    for window in windows:
        start_raw = window.get("start")
        end_raw = window.get("end")
        if not isinstance(start_raw, str) or not isinstance(end_raw, str):
            continue
        start = time.fromisoformat(start_raw)
        end = time.fromisoformat(end_raw)
        if start <= now_local_time <= end:
            return True
    return False


def _todays_auto_approvals(
    db: Session, *, policy_id: uuid.UUID, today: date
) -> list[OrderApproval]:
    return list(
        db.scalars(
            select(OrderApproval).where(
                OrderApproval.auto_policy_version_id == policy_id,
                func.date(OrderApproval.requested_at) == today,
                OrderApproval.status != OrderApprovalStatus.REJECTED,
            )
        ).all()
    )


def _notional_for_approval(db: Session, approval: OrderApproval) -> Decimal:
    bound_fields = db.scalar(
        select(ApprovalBoundFields).where(ApprovalBoundFields.order_approval_id == approval.id)
    )
    if bound_fields is None:
        return Decimal(0)
    if bound_fields.max_notional is not None:
        return bound_fields.max_notional
    price = bound_fields.limit_price or Decimal(0)
    return price * bound_fields.quantity


def evaluate_auto_policy_conditions(
    db: Session,
    *,
    policy: PaperAutoPolicyVersionModel,
    strategy_family: StrategyFamily,
    score: Decimal,
    order_type_value: str,
    proposed_notional: Decimal,
    per_order_risk_pct: Decimal,
    now: datetime | None = None,
) -> AutoPolicyEvaluation:
    """Checks every field the user configured (Revision Prompt 10's own
    list) — every failing condition is named, never a bare `False`."""
    now = now or datetime.now(UTC)
    failed: list[str] = []

    if not policy.enabled:
        failed.append("policy is not enabled")
    if strategy_family.value not in policy.eligible_strategy_families:
        failed.append(
            f"strategy {strategy_family.value} is not in the eligible list "
            f"{policy.eligible_strategy_families}"
        )
    if score < policy.min_score:
        failed.append(f"score {score} is below the configured minimum {policy.min_score}")
    if order_type_value not in policy.allowed_order_types:
        failed.append(
            f"order_type {order_type_value} is not in the allowed list {policy.allowed_order_types}"
        )
    now_local_time = now.astimezone(DISPLAY_TIMEZONE).time()
    if not _within_allowed_time_window(policy.allowed_time_windows, now_local_time):
        failed.append(f"{now_local_time.isoformat()} is outside every allowed time window")
    if per_order_risk_pct > policy.max_per_order_risk_pct:
        failed.append(
            f"per-order risk {per_order_risk_pct}% exceeds the configured maximum "
            f"{policy.max_per_order_risk_pct}%"
        )

    todays_approvals = _todays_auto_approvals(db, policy_id=policy.id, today=now.date())
    if len(todays_approvals) >= policy.max_orders_per_day:
        failed.append(
            f"{len(todays_approvals)} automatic order(s) already placed today "
            f"(maximum {policy.max_orders_per_day})"
        )
    todays_notional = sum((_notional_for_approval(db, a) for a in todays_approvals), Decimal(0))
    if todays_notional + proposed_notional > policy.max_daily_notional:
        failed.append(
            f"today's notional {todays_notional} + this order's {proposed_notional} would "
            f"exceed the configured maximum {policy.max_daily_notional}"
        )

    return AutoPolicyEvaluation(eligible=not failed, failed_conditions=failed)


def evaluate_auto_submission(
    db: Session,
    *,
    policy: PaperAutoPolicyVersionModel,
    strategy_family: StrategyFamily,
    score: Decimal,
    order_type_value: str,
    proposed_notional: Decimal,
    per_order_risk_pct: Decimal,
    hard_veto_results: list[VetoResult],
    now: datetime | None = None,
) -> AutoPolicyEvaluation:
    """The one function a caller should actually gate an automatic
    submission on — combines `evaluate_auto_policy_conditions()` with the
    hard-veto results via a plain AND, so "never overrides a hard risk
    or data-quality gate" cannot be bypassed by only checking the policy
    half."""
    policy_result = evaluate_auto_policy_conditions(
        db,
        policy=policy,
        strategy_family=strategy_family,
        score=score,
        order_type_value=order_type_value,
        proposed_notional=proposed_notional,
        per_order_risk_pct=per_order_risk_pct,
        now=now,
    )
    if any_veto_triggered(hard_veto_results):
        veto_reasons = [f"hard veto: {v.veto_code}" for v in hard_veto_results if v.triggered]
        return AutoPolicyEvaluation(
            eligible=False, failed_conditions=policy_result.failed_conditions + veto_reasons
        )
    return policy_result


def orders_open_under_policy(db: Session, *, policy_id: uuid.UUID) -> list[Order]:
    """Every still-open (`SUBMITTED`/`PARTIALLY_FILLED`) order whose
    approval was auto-submitted under this policy — what
    `KillSwitchBehavior.HALT_AND_CANCEL_OPEN` acts on when the kill
    switch fires while this policy is active."""
    approval_ids = db.scalars(
        select(OrderApproval.id).where(OrderApproval.auto_policy_version_id == policy_id)
    ).all()
    if not approval_ids:
        return []

    order_ids = db.scalars(
        select(BrokerSubmissionAttempt.resulting_order_id).where(
            BrokerSubmissionAttempt.order_approval_id.in_(approval_ids),
            BrokerSubmissionAttempt.resulting_order_id.is_not(None),
        )
    ).all()
    if not order_ids:
        return []
    return list(
        db.scalars(
            select(Order).where(
                Order.id.in_(order_ids),
                Order.status.in_((OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)),
            )
        ).all()
    )
