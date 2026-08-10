from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingos_api.routers import (
    alerts,
    backtests,
    committee,
    earnings,
    event_backtests,
    feature_diagnostics,
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
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(instruments.router)
app.include_router(watchlists.router)
app.include_router(market.router)
app.include_router(recommendations.router)
app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(journal.router)
app.include_router(performance.router)
app.include_router(alerts.router)
app.include_router(plans.router)
app.include_router(backtests.router)
app.include_router(settings.router)
app.include_router(morning_plan.router)
app.include_router(investment.router)
app.include_router(tactical.router)
app.include_router(earnings.router)
app.include_router(order_authority.proposals_router)
app.include_router(order_authority.approvals_router)
app.include_router(provider_diagnostics.router)
app.include_router(feature_diagnostics.router)
app.include_router(committee.router)
app.include_router(paper_auto_policy.router)
app.include_router(monitoring.router)
app.include_router(event_backtests.router)
