"""Four-tier order-authority policy (PROJECT_INSTRUCTIONS.md, "TradingOS
v2 Decision and Execution Amendment" -> ORDER AUTHORITY).

`assert_order_authorized()` is the one deterministic gate every future
order-submission code path (paper or live) must call before reaching the
broker boundary. No mode here can be satisfied by an LLM, a scheduled
job, an email, a news item, or any other external text — every argument
is a typed, code-constructed value, never a string parsed out of a
prompt or a message body.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


# Fully autonomous live entry is outside the approved scope (the
# amendment's own words) — there is deliberately no `LIVE_AUTO_POLICY`
# member. `test_policy_order_authority.py::test_exactly_four_modes_no_live_auto`
# guards against one ever being added silently.
class OrderAuthorityMode(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_MANUAL_APPROVAL = "PAPER_MANUAL_APPROVAL"
    PAPER_AUTO_POLICY = "PAPER_AUTO_POLICY"
    LIVE_CONFIRM_EACH_ORDER = "LIVE_CONFIRM_EACH_ORDER"


class OrderAuthorityDenied(Exception):
    """Raised whenever a proposed order does not clear this mode's gate.
    Every raise site below is fail-closed: an ambiguous or missing input
    is always treated as "not authorized," never defaulted to permissive.
    """


@dataclass(frozen=True)
class OrderConfirmation:
    """A human confirmation immediately preceding one order action.
    `account_id`/`environment`/`broker_endpoint` must be unambiguous —
    the amendment's "if live mode, account identity, environment, or
    broker endpoint is ambiguous, fail closed" requirement."""

    confirmed_at: datetime
    account_id: str
    environment: str
    broker_endpoint: str


@dataclass(frozen=True)
class AutoPolicyGrant:
    """The explicitly-enabled, versioned policy PAPER_AUTO_POLICY
    requires — an unversioned or disabled grant is not a grant."""

    policy_version: str
    enabled: bool


# A "fresh" confirmation for a live order — chosen short enough that a
# confirmation click can't be captured and replayed against a materially
# later market/account state. Configurable in a future phase; not a
# magic number silently relied on elsewhere.
MAX_LIVE_CONFIRMATION_AGE = timedelta(seconds=60)

_PROTECTIVE_LEG_ROLES = frozenset({"STOP_LOSS", "TAKE_PROFIT", "TRAILING", "OCO"})


def assert_order_authorized(
    mode: OrderAuthorityMode,
    *,
    is_live: bool,
    confirmation: OrderConfirmation | None = None,
    auto_policy: AutoPolicyGrant | None = None,
    now: datetime | None = None,
) -> None:
    """Raise `OrderAuthorityDenied` unless `mode` currently authorizes this
    one order action. Callers pass exactly what they have — this function
    never queries anything, so it cannot itself become a hidden broker
    boundary."""
    now = now or datetime.now(UTC)

    if mode is OrderAuthorityMode.RESEARCH_ONLY:
        raise OrderAuthorityDenied("RESEARCH_ONLY cannot create broker orders")

    if is_live and mode is not OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER:
        raise OrderAuthorityDenied(
            f"{mode.value} is not authorized to place a live order — only "
            "LIVE_CONFIRM_EACH_ORDER may, and only per-order"
        )

    if mode is OrderAuthorityMode.PAPER_MANUAL_APPROVAL and confirmation is None:
        raise OrderAuthorityDenied("PAPER_MANUAL_APPROVAL requires an explicit confirmation")

    if mode is OrderAuthorityMode.PAPER_AUTO_POLICY:
        if auto_policy is None or not auto_policy.enabled or not auto_policy.policy_version:
            raise OrderAuthorityDenied(
                "PAPER_AUTO_POLICY requires an explicitly enabled, versioned policy"
            )

    if mode is OrderAuthorityMode.LIVE_CONFIRM_EACH_ORDER:
        if confirmation is None:
            raise OrderAuthorityDenied("LIVE_CONFIRM_EACH_ORDER requires a confirmation")
        if (
            not confirmation.account_id
            or not confirmation.environment
            or not confirmation.broker_endpoint
        ):
            raise OrderAuthorityDenied(
                "ambiguous account identity, environment, or broker endpoint — failing closed"
            )
        age = now - confirmation.confirmed_at
        if age > MAX_LIVE_CONFIRMATION_AGE or age < timedelta(0):
            raise OrderAuthorityDenied(
                f"confirmation is not fresh ({age} old, max {MAX_LIVE_CONFIRMATION_AGE})"
            )


def bracket_leg_requires_its_own_confirmation(leg_role: str, *, primary_confirmed: bool) -> bool:
    """A user-confirmed bracket's protective legs (stop/target/trailing/
    OCO) may remain active at the broker without a second confirmation —
    only the primary entry (or a discretionary change to a leg) needs
    one. `leg_role` is a free string, not `models.enums.OrderLegRole`,
    since the amendment's TRAILING/OCO concepts don't exist as schema
    values yet (today's `OrderLegRole` only has PRIMARY/STOP_LOSS/
    TAKE_PROFIT) — this function is written against the amendment's
    eventual vocabulary, not today's narrower enum."""
    if leg_role in _PROTECTIVE_LEG_ROLES and primary_confirmed:
        return False
    return True
