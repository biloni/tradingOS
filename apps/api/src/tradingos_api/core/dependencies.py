from tradingos_api.core.config import get_settings
from tradingos_api.providers.alpaca_paper_broker import AlpacaPaperBrokerProvider
from tradingos_api.providers.broker import PaperBrokerProvider


def get_broker_provider() -> PaperBrokerProvider:
    """FastAPI dependency, overridable in tests (see
    tests/test_paper_orders_endpoints.py) so endpoint tests never need a
    real Alpaca connection."""
    return AlpacaPaperBrokerProvider(get_settings())
