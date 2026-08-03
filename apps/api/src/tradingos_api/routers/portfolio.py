from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_broker_provider
from tradingos_api.db.session import get_db
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.schemas.portfolio import PortfolioSnapshotOut
from tradingos_api.schemas.reconciliation import ReconciliationRowOut
from tradingos_api.services.portfolio import get_or_create_default_portfolio, get_portfolio_snapshot
from tradingos_api.services.reconciliation import reconcile_positions

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioSnapshotOut)
def get_portfolio(session: Annotated[Session, Depends(get_db)]) -> PortfolioSnapshotOut:
    portfolio = get_or_create_default_portfolio(session)
    return get_portfolio_snapshot(session, portfolio)


@router.get("/reconciliation", response_model=list[ReconciliationRowOut])
def get_portfolio_reconciliation(
    session: Annotated[Session, Depends(get_db)],
    broker: Annotated[PaperBrokerProvider, Depends(get_broker_provider)],
) -> list[ReconciliationRowOut]:
    """Phase 3's explicit reconciliation deliverable: our derived positions
    vs. what Alpaca's paper account actually reports."""
    portfolio = get_or_create_default_portfolio(session)
    return reconcile_positions(session, portfolio.id, broker)
