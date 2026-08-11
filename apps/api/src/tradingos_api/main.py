from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingos_api.core.dependencies import require_session
from tradingos_api.routers import (
    alerts,
    auth,
    backtests,
    committee,
    earnings,
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

app = FastAPI(title="TradingOS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
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
app.include_router(paper_auto_policy.router, dependencies=_AUTH)
app.include_router(monitoring.router, dependencies=_AUTH)
app.include_router(event_backtests.router, dependencies=_AUTH)
app.include_router(governance.router, dependencies=_AUTH)
