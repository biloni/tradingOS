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


class BrokerCapabilityProvider(Protocol):
    """No `submit_order`/`cancel_order` method exists on this interface,
    deliberately — see `providers/broker.py` for the (paper-only) order-
    submission interface. This one only ever answers "what can this
    broker connection do," for the provider-diagnostics dashboard."""

    def get_capabilities(self) -> BrokerCapabilities: ...
