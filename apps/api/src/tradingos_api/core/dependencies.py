import uuid
from decimal import Decimal

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from tradingos_api.core.auth import (
    SESSION_COOKIE_NAME,
    get_valid_session,
    touch_session,
    verify_csrf_token,
)
from tradingos_api.core.config import get_settings
from tradingos_api.db.session import get_db
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


def require_session(request: Request, db: Session = Depends(get_db)) -> None:
    """Revision Prompt 16, ADR-066 — the auth gate. Applied as a
    router-level dependency (`dependencies=[Depends(require_session)]`
    on every `app.include_router(...)` call in `main.py` except `auth`
    and `health`) rather than raw ASGI middleware, deliberately: a
    dependency participates in FastAPI's normal `Depends(get_db)`
    resolution — including `app.dependency_overrides` in tests — so a
    session created via `POST /auth/login` inside a test is validated
    against the *same* test-transaction connection, not a second,
    independent one that can't see uncommitted savepoint data.
    Sets `request.state.user_id`/`session_id`/`stepped_up_at` on
    success; raises 401 otherwise — this is the only function in the
    codebase that ever validates a session."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    session = get_valid_session(db, raw_token=raw_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    verify_csrf_token(request)
    touch_session(db, session)
    db.commit()
    request.state.user_id = session.user_id
    request.state.session_id = session.id
    request.state.stepped_up_at = session.stepped_up_at


def get_current_user_id(request: Request) -> uuid.UUID:
    """Reads the `user_id` `require_session()` already validated and set
    on `request.state` — this function never re-validates a session
    itself. The 500 here is a genuine "this should be structurally
    impossible" signal (this dependency was used on a route not also
    gated by `require_session`), never a normal 401 substitute."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=500,
            detail="get_current_user_id() called on a route require_session() didn't gate.",
        )
    return uuid.UUID(str(user_id))
