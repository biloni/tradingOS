"""Macro and volatility-index provider interfaces (Revision Prompt 4,
docs/BLOCKING_DECISIONS.md #2). Kept separate — a caller building the
market-regime classification cares specifically about VIX-proxy level/
percentile/rate-of-change, distinct from the broader, open-ended set of
macro series `MacroProvider` covers."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities


class MacroProviderNotConfigured(RuntimeError):
    pass


class MacroProviderUnavailable(RuntimeError):
    pass


class MacroCapabilities(ProviderCapabilities):
    covered_series_codes: tuple[str, ...]


class MacroObservationRecord(PointInTimeEnvelope):
    series_code: str
    as_of: date
    value: str


class MacroProvider(Protocol):
    def get_capabilities(self) -> MacroCapabilities: ...

    def get_series(
        self, series_code: str, start: date, end: date
    ) -> list[MacroObservationRecord]: ...


class VolatilityIndexProviderNotConfigured(RuntimeError):
    pass


class VolatilityIndexProviderUnavailable(RuntimeError):
    pass


class VolatilityIndexCapabilities(ProviderCapabilities):
    """`is_spot_index=False` for an ETP-proxy implementation (e.g. VIXY,
    docs/PROVIDER_MATRIX.md's recommended default) — an honest capability
    flag, since an ETP tracks futures, not the spot CBOE index tick-for-
    tick (a documented approximation, not a defect to hide)."""

    is_spot_index: bool
    supports_term_structure: bool


class VolatilityIndexRecord(PointInTimeEnvelope):
    as_of: date
    level: str


class VolatilityIndexProvider(Protocol):
    def get_capabilities(self) -> VolatilityIndexCapabilities: ...

    def get_level(self, as_of: date) -> VolatilityIndexRecord | None: ...
