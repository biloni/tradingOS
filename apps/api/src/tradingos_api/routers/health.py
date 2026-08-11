"""Liveness (`/health`) and readiness (`/ready`) — Revision Prompt 16.
Both are deliberately exempt from `require_session` (see `main.py`):
an infra orchestrator polling liveness/readiness has no credentials and
shouldn't need any.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.core.scheduler import get_scheduler_status
from tradingos_api.db.session import get_db

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    time_utc: str


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Pure liveness — no dependency checks, deliberately. A container
    orchestrator's liveness probe should only ever fail (and restart
    the process) when the process itself is wedged, not because a
    downstream dependency (DB, Alpaca, Anthropic) is degraded — that's
    what `/ready` is for."""
    return HealthResponse(status="ok", time_utc=datetime.now(UTC).isoformat())


class DependencyCheck(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    time_utc: str
    checks: dict[str, DependencyCheck]


@router.get("/ready", response_model=ReadinessResponse)
def get_readiness(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    """Reports the real state of every dependency this app has —
    honestly, not optimistically. `database` is the only *hard*
    dependency (its failure sets `ready=False` and a 503 status): the
    app cannot serve a single real request without it. The provider/
    LLM checks are informational, not blocking — this app is built to
    degrade gracefully without Alpaca/Anthropic credentials (principle
    5; `core/dependencies.py`'s provider fallbacks), so their absence
    is a real, reportable fact but not an outage. `scheduler`/`worker`
    report the real state of `core/scheduler.py`'s in-process
    APScheduler (task: real always-on scheduler/worker process) —
    `not_running` (not faked as healthy) whenever `SCHEDULER_ENABLED=false`
    or the app's lifespan hasn't started it yet (e.g. this process was
    imported without ever running its ASGI lifespan, as in some test
    setups), never silently reported as `ok` just because the process
    itself is up.
    """
    settings = get_settings()
    checks: dict[str, DependencyCheck] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = DependencyCheck(status="ok")
    except Exception as exc:  # noqa: BLE001 - readiness must report, never crash, the caller's failure
        checks["database"] = DependencyCheck(status="error", detail=str(exc))

    # Same fields/semantics as `routers/settings.py::list_provider_status`'s
    # `has_credential_configured` — deliberately not a second vocabulary
    # for the same underlying fact.
    alpaca_configured = bool(settings.alpaca_api_key_id and settings.alpaca_api_secret_key)
    checks["market_data_provider"] = DependencyCheck(
        status="configured" if alpaca_configured else "not_configured",
        detail=None if alpaca_configured else "falls back to SyntheticMarketQuoteProvider",
    )
    checks["broker_provider"] = DependencyCheck(
        status="configured" if alpaca_configured else "not_configured",
        detail=None if alpaca_configured else "falls back to SyntheticPaperBrokerProvider",
    )

    anthropic_configured = bool(settings.anthropic_api_key)
    checks["llm_provider"] = DependencyCheck(
        status="configured" if anthropic_configured else "not_configured",
        detail=(
            None
            if anthropic_configured
            else "NL-query/agent features return a clear 503, not a crash"
        ),
    )

    scheduler_status = get_scheduler_status()
    checks["scheduler"] = DependencyCheck(
        status="ok" if scheduler_status.running else "not_running",
        detail=(
            f"in-process APScheduler polling decide_schedule()/"
            f"decide_reconciliation_schedule() every "
            f"{scheduler_status.tick_interval_seconds}s ({scheduler_status.tick_count} "
            f"tick(s) so far)"
            if scheduler_status.running
            else "SCHEDULER_ENABLED=false, or this process's lifespan hasn't started it"
        ),
    )
    checks["worker"] = DependencyCheck(
        status="ok" if scheduler_status.running else "not_running",
        detail=(
            f"last tick at {scheduler_status.last_tick_at.isoformat()}"
            + (
                f"; last tick had errors: {scheduler_status.last_tick_error}"
                if scheduler_status.last_tick_error
                else ""
            )
            if scheduler_status.last_tick_at
            else "no tick has run yet"
        ),
    )

    ready = checks["database"].status == "ok"
    response.status_code = 200 if ready else 503
    return ReadinessResponse(ready=ready, time_utc=datetime.now(UTC).isoformat(), checks=checks)
