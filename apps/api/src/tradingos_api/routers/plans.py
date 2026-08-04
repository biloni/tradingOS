"""Daily plans (docs/API_CONTRACTS.md area 10)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import AlertStatus
from tradingos_api.models.market_evidence import MarketRegimeSnapshot
from tradingos_api.models.operations import Alert
from tradingos_api.models.recommendations import Recommendation
from tradingos_api.models.security_master import Instrument
from tradingos_api.routers.recommendations import _latest_version, _version_response
from tradingos_api.schemas.alerts import AlertResponse
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.market import RegimeResponse
from tradingos_api.schemas.plans import DailyPlanResponse
from tradingos_api.schemas.recommendations import RecommendationSummaryResponse

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.get("/daily", response_model=DailyPlanResponse)
def get_daily_plan(
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
    as_of: date | None = Query(default=None, description="Defaults to today"),
) -> DailyPlanResponse:
    target_date = as_of or datetime.utcnow().date()
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    regime = db.scalar(
        select(MarketRegimeSnapshot).where(MarketRegimeSnapshot.as_of == target_date)
    )

    recs = db.scalars(
        select(Recommendation).where(
            Recommendation.opened_at >= day_start, Recommendation.opened_at <= day_end
        )
    ).all()
    rec_summaries: list[RecommendationSummaryResponse] = []
    for rec in recs:
        inst = db.get(Instrument, rec.instrument_id)
        assert inst is not None
        latest = _latest_version(db, rec.id)
        rec_summaries.append(
            RecommendationSummaryResponse(
                id=rec.id,
                instrument=InstrumentResponse.model_validate(inst),
                status=rec.status,
                opened_at=rec.opened_at,
                latest_version=_version_response(db, latest) if latest else None,
            )
        )

    open_alerts = db.scalars(
        select(Alert).where(Alert.owner_user_id == owner_user_id, Alert.status == AlertStatus.OPEN)
    ).all()

    return DailyPlanResponse(
        as_of=target_date,
        regime=RegimeResponse.model_validate(regime) if regime else None,
        recommendations=rec_summaries,
        open_alerts=[AlertResponse.model_validate(a) for a in open_alerts],
    )
