from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import ask_rate_limiter
from tradingos_api.db.session import get_db
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.ask import AskRequest
from tradingos_api.services.ask import AskResponse, answer_question

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(
    body: AskRequest,
    session: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AskResponse:
    """Natural-language query over the trading dataset: synthesis and
    explanation only, grounded in tool results (services/llm_tools.py) —
    never text-to-SQL, never the source of numeric truth (principles 6/7)."""
    if not ask_rate_limiter.try_acquire():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for /api/v1/ask. Please wait a few seconds and retry.",
        )
    return answer_question(session, llm, body.question)
