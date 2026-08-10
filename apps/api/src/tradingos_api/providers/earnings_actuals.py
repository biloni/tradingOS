"""Reported-actuals provider interface (Revision Prompt 11) — "ingest and
validate official results" is step 2 of the POST-EARNINGS WORKFLOW. Mirrors
`providers/earnings_consensus.py`'s shape (same point-in-time envelope,
same Protocol style) but describes ground-truth reported figures, not an
analyst estimate: `EarningsActualRecord.source_type` is restricted to
`"official_ir_release"` or `"regulatory_filing"` at the type level, the
same source-priority-1 restriction `providers/official_evidence.py`
already enforces for guidance — an actual EPS/revenue number must never
be constructible from a wire-service paraphrase or an analyst's
back-calculation.
"""

from __future__ import annotations

from typing import Literal, Protocol

from tradingos_api.providers.point_in_time import PointInTimeEnvelope, ProviderCapabilities

ActualsSourceType = Literal["official_ir_release", "regulatory_filing"]


class EarningsActualsProviderNotConfigured(RuntimeError):
    pass


class EarningsActualsProviderUnavailable(RuntimeError):
    pass


class EarningsActualsCapabilities(ProviderCapabilities):
    supports_revenue_actual: bool


class EarningsActualRecord(PointInTimeEnvelope):
    ticker: str
    fiscal_period: str
    metric: Literal["eps", "revenue"]
    actual_value: str
    source_type: ActualsSourceType


class EarningsActualsProvider(Protocol):
    def get_capabilities(self) -> EarningsActualsCapabilities: ...

    def get_actuals(self, ticker: str, fiscal_period: str) -> list[EarningsActualRecord]:
        """Empty list, not a fabricated entry, when results for the
        requested period have not yet been officially released — this is
        the schema-level fact `services/post_earnings_workflow.py` reads
        to decide `WAITING_FOR_DATA` (Prompt 11 CRITICAL RULES: "if
        official results ... are delayed show WAITING_FOR_DATA")."""
        ...
