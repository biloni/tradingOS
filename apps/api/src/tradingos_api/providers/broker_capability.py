"""Broker capability provider interface (Revision Prompt 4). Purely
diagnostic — reports what a broker connection *can* do (paper-only vs.
live-capable, supported order types, extended-hours support), never
submits, modifies, or cancels an order. This is deliberately a read-only
sibling to `providers/broker.py`'s `PaperBrokerProvider` (which actually
submits paper orders) — a capability query must never itself be able to
reach the broker boundary in a way OA-7 would care about.
"""

from __future__ import annotations

from typing import Protocol

from tradingos_api.providers.point_in_time import ProviderCapabilities


class BrokerCapabilityProviderNotConfigured(RuntimeError):
    pass


class BrokerCapabilityProviderUnavailable(RuntimeError):
    pass


class BrokerCapabilities(ProviderCapabilities):
    supports_live_trading: bool
    supports_paper_trading: bool
    supported_order_types: tuple[str, ...]
    supports_extended_hours: bool
    supports_fractional_shares: bool
    # Revision Prompt 10 — "prefer broker-native bracket/OCO when
    # supported." `services/bracket_execution.py` reads this to decide
    # whether a stop+target request can go through in one native broker
    # call or must fall back to independently-tracked emulated legs
    # (`OrderLeg.bracket_group_id`, Phase 8) with a disclosed reliability
    # limitation.
    supports_native_brackets: bool = False


class BrokerCapabilityProvider(Protocol):
    """No `submit_order`/`cancel_order` method exists on this interface,
    deliberately — see `providers/broker.py` for the (paper-only) order-
    submission interface. This one only ever answers "what can this
    broker connection do," for the provider-diagnostics dashboard."""

    def get_capabilities(self) -> BrokerCapabilities: ...
