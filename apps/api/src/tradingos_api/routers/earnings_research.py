"""`POST /api/v1/earnings-research` — on-demand, live-web-search research
for any current S&P 500 / Dow / Nasdaq-100 company (not restricted to
this app's own tracked-instrument universe). Rate-limited separately
from `/ask` (`core/rate_limit.py::earnings_research_rate_limiter`) since
each call can trigger several real web searches, not just one model
call."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import earnings_research_rate_limiter
from tradingos_api.db.session import get_db
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.earnings_research import (
    EarningsResearchRequest,
    EarningsResearchResponse,
)
from tradingos_api.services.earnings_research import research_company

router = APIRouter(prefix="/api/v1/earnings-research", tags=["earnings-research"])


@router.post("", response_model=EarningsResearchResponse)
def earnings_research(
    payload: EarningsResearchRequest,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> EarningsResearchResponse:
    if not earnings_research_rate_limiter.try_acquire():
        raise HTTPException(
            status_code=429,
            detail=(
                "You're requesting research faster than the configured limit — "
                "wait a few seconds and try again."
            ),
        )
    return research_company(db, llm, payload.company)


__all__ = ["router"]
