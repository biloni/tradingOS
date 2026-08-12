import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tradingos_api.core.config import get_settings
from tradingos_api.core.dependencies import require_session
from tradingos_api.core.logging import configure_logging
from tradingos_api.core.request_id_middleware import RequestIdMiddleware
from tradingos_api.core.scheduler import start_scheduler, stop_scheduler
from tradingos_api.core.security_headers import SecurityHeadersMiddleware
from tradingos_api.routers import (
    alerts,
    ask,
    auth,
    backtests,
    committee,
    earnings,
    earnings_research,
    event_backtests,
    feature_diagnostics,
    governance,
    health,
    instruments,
    investment,
    journal,
    market,
    monitoring,
    morning_plan,
    ops,
    order_authority,
    orders,
    paper_auto_policy,
    performance,
    plans,
    portfolio,
    provider_diagnostics,
    recommendations,
    settings,
    tactical,
    watchlists,
)

configure_logging()
_logger = logging.getLogger("tradingos_api")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Revision Prompt 16, task: real always-on scheduler/worker
    process. Starlette's `TestClient` only runs lifespan startup/shutdown
    when entered as a context manager (`with TestClient(app) as c:`);
    this project's `tests/conftest.py::client` fixture deliberately
    never does that, so the scheduler never starts under pytest — see
    `core/scheduler.py`'s own docstring for the full reasoning."""
    if get_settings().scheduler_enabled:
        start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="TradingOS API", version="0.1.0", lifespan=_lifespan)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Revision Prompt 16 — every route that raises `HTTPException` (the
    overwhelming majority of expected error cases in this app) is
    handled by FastAPI's own default handler and never reaches this
    one; Starlette resolves exception handlers by the most specific
    matching type, so registering `Exception` here only catches what
    nothing more specific already claimed. Logs the real exception with
    full context server-side (through the redacting formatter — see
    `core/logging.py`) while the client only ever sees a generic
    message: an unhandled exception's `repr()`/traceback could contain
    anything (a raw SQL error with row data, an object repr with a
    field that happens to be sensitive), so it is never echoed back."""
    _logger.exception(
        "unhandled exception",
        exc_info=exc,
        extra={"http_method": request.method, "path": request.url.path},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# Registered first so it's the outermost layer (Starlette wraps
# middleware in reverse-add order) — every request, including ones
# CORS itself rejects, gets a request ID and an access-log line.
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

# Revision Prompt 16, ADR-066 — "validate every boundary." Every router
# below except `auth` (login must be reachable while unauthenticated)
# and `health` (liveness/readiness must be checkable by an
# orchestrator with no credentials) requires a valid session,
# via `core/dependencies.py::require_session()` applied at the router
# level rather than global middleware — see that function's own
# docstring for why (test-transaction visibility). `/docs`/`/openapi.json`/
# `/redoc` are FastAPI's own auto-registered routes, never passed
# through `include_router()`, so they are never gated here — a
# deliberate, documented exception (docs/SECURITY.md), not an
# oversight: this app is not intended for public internet exposure
# regardless (docs/THREAT_MODEL.md's own scope statement).
_AUTH = [Depends(require_session)]

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(instruments.router, dependencies=_AUTH)
app.include_router(watchlists.router, dependencies=_AUTH)
app.include_router(market.router, dependencies=_AUTH)
app.include_router(recommendations.router, dependencies=_AUTH)
app.include_router(portfolio.router, dependencies=_AUTH)
app.include_router(orders.router, dependencies=_AUTH)
app.include_router(journal.router, dependencies=_AUTH)
app.include_router(performance.router, dependencies=_AUTH)
app.include_router(alerts.router, dependencies=_AUTH)
app.include_router(plans.router, dependencies=_AUTH)
app.include_router(backtests.router, dependencies=_AUTH)
app.include_router(settings.router, dependencies=_AUTH)
app.include_router(morning_plan.router, dependencies=_AUTH)
app.include_router(investment.router, dependencies=_AUTH)
app.include_router(tactical.router, dependencies=_AUTH)
app.include_router(earnings.router, dependencies=_AUTH)
app.include_router(order_authority.proposals_router, dependencies=_AUTH)
app.include_router(order_authority.approvals_router, dependencies=_AUTH)
app.include_router(provider_diagnostics.router, dependencies=_AUTH)
app.include_router(feature_diagnostics.router, dependencies=_AUTH)
app.include_router(committee.router, dependencies=_AUTH)
app.include_router(ask.router, dependencies=_AUTH)
app.include_router(earnings_research.router, dependencies=_AUTH)
app.include_router(paper_auto_policy.router, dependencies=_AUTH)
app.include_router(monitoring.router, dependencies=_AUTH)
app.include_router(event_backtests.router, dependencies=_AUTH)
app.include_router(governance.router, dependencies=_AUTH)
app.include_router(ops.router, dependencies=_AUTH)
