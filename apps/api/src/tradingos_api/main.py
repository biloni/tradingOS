from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradingos_api.routers import health, symbols

app = FastAPI(title="TradingOS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(symbols.router)
