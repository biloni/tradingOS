"""Options-implied expected-move provider interface (Revision Prompt 4).
Feeds `EventExpectedMoveSnapshot.option_implied_move_pct` — one of three
inputs alongside ATR-based and historical-gap-based move estimates
(`services/ingest_evidence.py` selects among them); this interface is
optional by design ("options-implied move if the approved provider
supports it") — a caller must check `get_capabilities().is_available`
before calling `get_expected_move()` and must not treat a missing
capability as zero expected move."""

from __future__ import annotations

from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class OptionsExpectedMoveProviderNotConfigured(RuntimeError):
    pass


class OptionsExpectedMoveProviderUnavailable(RuntimeError):
    pass


class OptionsExpectedMoveCapabilities(ProviderCapabilities):
    is_available: bool
    """`False` for an implementation with no real options-chain access —
    the honest default until a real vendor is contracted."""


class OptionsExpectedMoveRecord(PointInTimeEnvelope):
    ticker: str
    expected_move_pct: str
    reference_event_date: str
    """The earnings (or other event) date this expected move was priced
    against — required so `services/data_quality.py`'s "implied move
    timestamp inconsistent with planned entry" gate has something
    concrete to compare against."""


class OptionsExpectedMoveProvider(Protocol):
    def get_capabilities(self) -> OptionsExpectedMoveCapabilities: ...

    def get_expected_move(
        self, ticker: str, reference_event_date: str
    ) -> OptionsExpectedMoveRecord | None: ...
