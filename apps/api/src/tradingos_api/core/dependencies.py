import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
from tradingos_api.models.identity import UserProfile
from tradingos_api.providers.alpaca_paper_broker import AlpacaPaperBrokerProvider
from tradingos_api.providers.anthropic_llm import AnthropicLLMProvider
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.providers.llm import LLMProvider, LLMProviderNotConfigured


def get_broker_provider() -> PaperBrokerProvider:
    """FastAPI dependency, overridable in tests (see
    tests/test_paper_orders_endpoints.py) so endpoint tests never need a
    real Alpaca connection."""
    return AlpacaPaperBrokerProvider(get_settings())


def get_llm_provider() -> LLMProvider:
    """FastAPI dependency, overridable in tests (see
    tests/test_ask_endpoint.py) so endpoint tests never need a real
    Anthropic API key. Turns a missing `ANTHROPIC_API_KEY` into a clear 503
    (principle 5: graceful degradation, never a raw crash) instead of an
    unhandled exception during dependency resolution."""
    try:
        return AnthropicLLMProvider(get_settings())
    except LLMProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_current_user_id(db: Session = Depends(get_db)) -> uuid.UUID:
    """The single seeded user (ADR-007 — no auth in this system). Every
    Phase 8 router depends on this rather than hardcoding a lookup, so a
    real multi-user auth layer only has to replace this one function.
    Raises 500 (not 404) if no user exists — this is a seed-data
    precondition, not a legitimate "not found" a client could hit."""
    user = db.query(UserProfile).first()
    if user is None:
        raise HTTPException(
            status_code=500,
            detail="No user_profile row exists — run the seed script (tradingos-seed).",
        )
    return user.id
