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

    database_url: str = "postgresql+psycopg://tradingos_app:@localhost:5432/tradingos"

    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
