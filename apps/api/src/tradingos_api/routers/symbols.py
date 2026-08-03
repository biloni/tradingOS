from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.indicator import Indicator
from tradingos_api.models.symbol import Symbol
from tradingos_api.schemas.indicator import IndicatorOut
from tradingos_api.schemas.price_bar import PriceBarOut
from tradingos_api.schemas.symbol import SymbolOut
from tradingos_api.services.price_bars import get_latest_price_bars

router = APIRouter(prefix="/api/v1/symbols", tags=["symbols"])

DEFAULT_BARS_LOOKBACK_DAYS = 90


def _get_symbol_or_404(session: Session, ticker: str) -> Symbol:
    symbol = session.execute(
        select(Symbol).where(Symbol.ticker == ticker.upper())
    ).scalar_one_or_none()
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    return symbol


@router.get("", response_model=list[SymbolOut])
def list_symbols(session: Annotated[Session, Depends(get_db)]) -> list[Symbol]:
    return list(session.execute(select(Symbol).order_by(Symbol.ticker)).scalars().all())


@router.get("/{ticker}/bars", response_model=list[PriceBarOut])
def get_symbol_bars(
    ticker: str,
    session: Annotated[Session, Depends(get_db)],
    start: date | None = None,
    end: date | None = None,
) -> list[PriceBarOut]:
    symbol = _get_symbol_or_404(session, ticker)
    end = end or date.today()
    start = start or (end - timedelta(days=DEFAULT_BARS_LOOKBACK_DAYS))
    bars = get_latest_price_bars(session, symbol.id, start, end)
    return [PriceBarOut.model_validate(bar) for bar in bars]


@router.get("/{ticker}/indicators", response_model=list[IndicatorOut])
def get_symbol_indicators(
    ticker: str,
    session: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
) -> list[IndicatorOut]:
    symbol = _get_symbol_or_404(session, ticker)

    if as_of is None:
        latest_as_of = session.execute(
            select(Indicator.as_of)
            .where(Indicator.symbol_id == symbol.id)
            .order_by(Indicator.as_of.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_as_of is None:
            return []
        as_of = latest_as_of

    rows = (
        session.execute(
            select(Indicator).where(Indicator.symbol_id == symbol.id, Indicator.as_of == as_of)
        )
        .scalars()
        .all()
    )
    return [IndicatorOut.model_validate(row) for row in rows]
