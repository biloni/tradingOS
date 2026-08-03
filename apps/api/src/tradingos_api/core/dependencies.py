from fastapi import HTTPException

from tradingos_api.core.config import get_settings
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
