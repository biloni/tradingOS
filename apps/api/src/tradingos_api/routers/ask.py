"""`POST /api/v1/ask` — natural-language query over the current
workforce of tracked instruments, recommendations, and earnings
(ADR-019). Rate-limited (`core/rate_limit.py::ask_rate_limiter`) to
bound Anthropic spend against a runaway client; the LLM dependency
degrades to a clear 503 rather than a raw crash when no
`ANTHROPIC_API_KEY` is configured (`core/dependencies.py::get_llm_provider`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import ask_rate_limiter
from tradingos_api.db.session import get_db
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.ask import AskRequest, AskResponse
from tradingos_api.services.ask import answer_question

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    if not ask_rate_limiter.try_acquire():
        raise HTTPException(
            status_code=429,
            detail=(
                "You're asking questions faster than the configured limit — "
                "wait a few seconds and try again."
            ),
        )
    return answer_question(db, llm, payload.question)


__all__ = ["router"]
