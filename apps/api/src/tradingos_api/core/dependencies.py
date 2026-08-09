import uuid
from decimal import Decimal

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
from tradingos_api.models.identity import UserProfile
from tradingos_api.providers.alpaca_evidence import (
    AlpacaBrokerCapabilityProvider,
    AlpacaStockDataProvider,
)
from tradingos_api.providers.alpaca_paper_broker import AlpacaPaperBrokerProvider
from tradingos_api.providers.anthropic_llm import AnthropicLLMProvider
from tradingos_api.providers.broker import BrokerProviderNotConfigured, PaperBrokerProvider
from tradingos_api.providers.broker_capability import (
    BrokerCapabilities,
    BrokerCapabilityProvider,
    BrokerCapabilityProviderNotConfigured,
)
from tradingos_api.providers.llm import LLMProvider, LLMProviderNotConfigured
from tradingos_api.providers.quotes_bars import MarketQuoteProvider
from tradingos_api.providers.synthetic_market_quote import SyntheticMarketQuoteProvider
from tradingos_api.providers.synthetic_paper_broker import (
    SyntheticBrokerCapabilityProvider,
    SyntheticPaperBrokerProvider,
)

# A small, curated reference-price fixture for this project's demo
# symbols (Revision Prompt 10) — used only by the synthetic fallbacks
# below, never by a real Alpaca-backed provider.
_SYNTHETIC_REFERENCE_PRICES: dict[str, Decimal] = {
    "AAPL": Decimal("230.00"),
    "AMD": Decimal("150.00"),
    "AMZN": Decimal("185.00"),
    "MRVL": Decimal("75.00"),
}


def get_broker_provider() -> PaperBrokerProvider:
    """FastAPI dependency, overridable in tests. Falls back to the
    deterministic `SyntheticPaperBrokerProvider` when no Alpaca paper
    credentials are configured (principle 5: graceful, honest
    degradation) — this is what lets `services/order_execution.py`'s
    full flow run and be demoed without a real Alpaca account, exactly
    matching Revision Prompt 4's synthetic-evidence-provider pattern."""
    try:
        return AlpacaPaperBrokerProvider(get_settings())
    except BrokerProviderNotConfigured:
        return SyntheticPaperBrokerProvider(reference_prices=_SYNTHETIC_REFERENCE_PRICES)


def get_broker_capability_provider() -> BrokerCapabilityProvider:
    """Mirrors `get_broker_provider()`'s fallback — a caller that needs
    to know `supports_native_brackets` (`services/bracket_execution.py`)
    gets an honest answer either way."""
    try:
        return AlpacaBrokerCapabilityProvider(get_settings())
    except BrokerCapabilityProviderNotConfigured:
        return SyntheticBrokerCapabilityProvider()


def get_broker_capabilities() -> BrokerCapabilities:
    return get_broker_capability_provider().get_capabilities()


def get_market_quote_provider() -> MarketQuoteProvider:
    """Same fallback pattern for the one quote
    `services/order_execution.py::refresh_and_recalculate()` needs
    immediately before submission — checked directly against
    `Settings` rather than try/except, the same style
    `routers/settings.py::list_provider_status()` already uses."""
    settings = get_settings()
    if settings.alpaca_api_key_id and settings.alpaca_api_secret_key:
        return AlpacaStockDataProvider(settings)
    return SyntheticMarketQuoteProvider(reference_prices=_SYNTHETIC_REFERENCE_PRICES)


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
