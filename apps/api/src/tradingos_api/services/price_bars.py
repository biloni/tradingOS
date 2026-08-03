from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.models.price_bar import PriceBar, Timeframe


def get_latest_price_bars(
    session: Session,
    symbol_id: int,
    start: date,
    end: date,
    timeframe: Timeframe = Timeframe.DAY,
) -> list[PriceBar]:
    """The one shared point-in-time derivation helper every caller
    (indicators, scoring, backtesting) reads latest prices through.

    `PriceBar` is append-only (see its docstring) — a correction is a new row
    with a later `fetched_at`, not an update in place. This picks the
    max-`fetched_at` row per `as_of` date, so "current" is always derived
    the same way everywhere, never re-implemented per caller.
    """
    latest_fetch = (
        select(PriceBar.as_of, func.max(PriceBar.fetched_at).label("max_fetched_at"))
        .where(
            PriceBar.symbol_id == symbol_id,
            PriceBar.timeframe == timeframe,
            PriceBar.as_of >= start,
            PriceBar.as_of <= end,
        )
        .group_by(PriceBar.as_of)
        .subquery()
    )

    stmt = (
        select(PriceBar)
        .join(
            latest_fetch,
            (PriceBar.as_of == latest_fetch.c.as_of)
            & (PriceBar.fetched_at == latest_fetch.c.max_fetched_at),
        )
        .where(PriceBar.symbol_id == symbol_id, PriceBar.timeframe == timeframe)
        .order_by(PriceBar.as_of)
    )
    return list(session.execute(stmt).scalars().all())
