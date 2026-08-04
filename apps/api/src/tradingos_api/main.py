from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingos_api.routers import (
    alerts,
    backtests,
    health,
    instruments,
    journal,
    market,
    orders,
    performance,
    plans,
    portfolio,
    recommendations,
    settings,
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
