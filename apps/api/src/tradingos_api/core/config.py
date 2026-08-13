from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


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

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url_driver(cls, value: str) -> str:
        """Managed-Postgres hosts (Railway, Heroku, etc.) hand out a bare
        `postgres://` or `postgresql://` connection string with no driver
        suffix. This project only installs `psycopg` (v3) — never the
        classic `psycopg2` — so without this normalization, SQLAlchemy's
        default driver resolution for the bare `postgresql` dialect
        (`psycopg2`) fails at engine-creation time with `ModuleNotFoundError`,
        crashing both the app (`db/session.py`) and migrations
        (`alembic/env.py`) on startup. Parsed via SQLAlchemy's own
        `make_url()` rather than a manual string-prefix check — that
        correctly handles drivername casing and leaves user/password/host/
        query untouched, so a value that already names a driver
        (`postgresql+psycopg://`, as local dev's own default above does,
        or an explicit `+psycopg2`/`+asyncpg`) is never rewritten."""
        url = make_url(value)
        if url.drivername.lower() in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
        return url.render_as_string(hide_password=False)

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

    # Revision Prompt 16, task: real always-on scheduler/worker process.
    # An in-process APScheduler instance (`core/scheduler.py`) starts
    # with the FastAPI app and polls `decide_schedule()`/
    # `decide_reconciliation_schedule()` every minute. Defaults on for
    # any real run of this process; set `SCHEDULER_ENABLED=false` to
    # run the API without it (e.g. a one-off script, or a demo that
    # drives its own fake clock and would otherwise race the real one).
    # Never auto-starts under pytest regardless of this flag — FastAPI's
    # `TestClient` only triggers lifespan startup/shutdown when entered
    # as a context manager (`with TestClient(app) as c:`), and this
    # project's `client` fixture (tests/conftest.py) deliberately never
    # does that.
    scheduler_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
