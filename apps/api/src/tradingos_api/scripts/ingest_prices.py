"""On-demand ingestion entrypoint: `uv run python -m
tradingos_api.scripts.ingest_prices` (or `uv run tradingos-ingest-prices`).

Upserts the seed `Symbol` universe, pulls ~2 years of daily bars per symbol
from Alpaca, inserts them as `PriceBar` rows, then computes and stores every
indicator in `services/indicators.py`.

No scheduler/background-job wiring yet (Redis/scheduling deferred per
ADR-006 — no demonstrated recurring need until this manual path is proven).
Re-running this script inserts a *new* `PriceBar` row per day with a later
`fetched_at` rather than upserting — `PriceBar` is append-only by design (see
its docstring); `get_latest_price_bars()` always resolves to the newest
fetch, so re-running is safe, just not space-efficient for repeated demo
runs.
"""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.db.session import SessionLocal
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.symbol import Symbol
from tradingos_api.providers.alpaca_market_data import AlpacaMarketDataProvider
from tradingos_api.providers.market_data import MarketDataProviderNotConfigured
from tradingos_api.seed_symbols import SEED_SYMBOLS
from tradingos_api.services.indicators import compute_indicators_for_symbol

BACKFILL_DAYS = 730


def _upsert_symbols(session: Session) -> dict[str, int]:
    rows = [
        {"ticker": ticker, "name": name, "exchange": exchange, "asset_type": asset_type}
        for ticker, name, exchange, asset_type in SEED_SYMBOLS
    ]
    stmt = insert(Symbol).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={
            "name": stmt.excluded.name,
            "exchange": stmt.excluded.exchange,
            "asset_type": stmt.excluded.asset_type,
        },
    )
    session.execute(stmt)
    session.commit()

    result = session.query(Symbol).filter(Symbol.ticker.in_([r["ticker"] for r in rows])).all()
    return {symbol.ticker: symbol.id for symbol in result}


def main() -> None:
    settings = get_settings()
    try:
        provider = AlpacaMarketDataProvider(settings)
    except MarketDataProviderNotConfigured as exc:
        print(f"Ingestion skipped: {exc}", file=sys.stderr)
        sys.exit(1)

    session = SessionLocal()
    try:
        ticker_to_id = _upsert_symbols(session)
        print(f"Upserted {len(ticker_to_id)} symbols.")

        end = datetime.now(UTC).date()
        start = end - timedelta(days=BACKFILL_DAYS)

        for ticker, symbol_id in ticker_to_id.items():
            bars = provider.get_daily_bars(ticker, start, end)
            if not bars:
                print(f"{ticker}: no bars returned.")
                continue

            session.add_all(
                PriceBar(
                    symbol_id=symbol_id,
                    as_of=bar.as_of,
                    timeframe=Timeframe.DAY,
                    open=Decimal(bar.open),
                    high=Decimal(bar.high),
                    low=Decimal(bar.low),
                    close=Decimal(bar.close),
                    volume=bar.volume,
                    source=bar.source,
                    adjustment="split",
                    fetched_at=datetime.fromisoformat(bar.fetched_at),
                )
                for bar in bars
            )
            session.commit()
            print(f"{ticker}: inserted {len(bars)} price bars.")

            indicator_count = compute_indicators_for_symbol(session, symbol_id, start, end)
            print(f"{ticker}: computed {indicator_count} new indicator rows.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
