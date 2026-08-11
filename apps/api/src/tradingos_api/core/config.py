from decimal import Decimal
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

    # Revision Prompt 16 — comma-separated allow-list, so a real
    # deployment (task: Dockerfiles + deployment docs) can point this at
    # its real frontend origin via env var alone, no code change. Local
    # dev's own frontend origin is the only default.
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    anthropic_api_key: str | None = None

    # Revision Prompt 16 — "cost budgets and kill switches." No fixed
    # figure is specified anywhere in this project's docs (PROVIDER_MATRIX.md
    # gives *monthly* planning estimates: Normal ~$8-17, Heavy ~$45-100);
    # $5/day (~$150/month) is a deliberately generous daily backstop —
    # well above the "Heavy" monthly tier if hit every day — chosen to
    # catch a genuine runaway loop, not to nag on ordinary heavy usage.
    # Override via env for a tighter personal limit.
    daily_llm_cost_budget_usd: Decimal = Decimal("5.00")


@lru_cache
def get_settings() -> Settings:
    return Settings()
