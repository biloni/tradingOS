from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from tradingos_api.schemas.alerts import AlertResponse
from tradingos_api.schemas.market import RegimeResponse
from tradingos_api.schemas.recommendations import RecommendationSummaryResponse


class DailyPlanResponse(BaseModel):
    """FR-28/FR-31 — one artifact per trading day, retrievable by date.
    This pass composes it live from stored rows on every request rather
    than persisting a `scheduled_artifact` snapshot (no scheduler exists
    yet, ADR-040 — ​a future phase would freeze this at premarket-job time
    instead of recomputing it)."""

    as_of: date
    regime: RegimeResponse | None
    recommendations: list[RecommendationSummaryResponse]
    open_alerts: list[AlertResponse]
