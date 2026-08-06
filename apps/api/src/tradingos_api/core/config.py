from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env.

    No default ever contains a real secret. Missing optional keys (Alpaca,
    Anthropic) are represented as None so provider code can degrade
    gracefully instead of crashing, per project principle 5.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"

    # Revision Prompt R2 scaffold: the server-side source of truth the
    # frontend's environment banner / operating-mode status component
    # reads (never client storage, per PROJECT_INSTRUCTIONS.md's v2
    # amendment OA-*). Deliberately just a config passthrough this pass —
    # `assert_order_authorized()` (policy/order_authority.py, R0) is not
    # yet wired to any router, so this value does not yet gate anything;
    # it only reports what mode the deployment is configured for.
    operating_mode: str = "RESEARCH_ONLY"

    database_url: str = "postgresql+psycopg://tradingos_app:@localhost:5432/tradingos"

    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
