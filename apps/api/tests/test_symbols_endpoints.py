"""Endpoint contract tests run against an in-memory SQLite database seeded
with a fake Symbol/PriceBar/Indicator dataset — no live Postgres, no network,
per the project's fixtures-not-live-APIs test policy."""

from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingos_api.db.base import Base
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.indicator import Indicator, IndicatorName
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.symbol import AssetType, Symbol


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    symbol = Symbol(
        ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", asset_type=AssetType.EQUITY
    )
    session.add(symbol)
    session.commit()
    session.refresh(symbol)

    # Two fetches for the same day: get_latest_price_bars must resolve to
    # the later one (append-only correction semantics).
    session.add(
        PriceBar(
            symbol_id=symbol.id,
            as_of=date(2026, 7, 1),
            timeframe=Timeframe.DAY,
            open=Decimal("99.0"),
            high=Decimal("100.0"),
            low=Decimal("98.5"),
            close=Decimal("99.5"),
            volume=1000,
            source="alpaca",
            adjustment="split",
            fetched_at=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        )
    )
    session.add(
        PriceBar(
            symbol_id=symbol.id,
            as_of=date(2026, 7, 1),
            timeframe=Timeframe.DAY,
            open=Decimal("99.0"),
            high=Decimal("100.0"),
            low=Decimal("98.5"),
            close=Decimal("100.25"),
            volume=1050,
            source="alpaca",
            adjustment="split",
            fetched_at=datetime(2026, 7, 1, 23, 0, tzinfo=UTC),
        )
    )
    session.add(
        Indicator(
            symbol_id=symbol.id,
            as_of=date(2026, 7, 1),
            indicator_name=IndicatorName.SMA_20,
            version="v1",
            value=Decimal("99.75"),
            computed_at=datetime(2026, 7, 1, 23, 5, tzinfo=UTC),
        )
    )
    session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


def test_list_symbols(client: TestClient) -> None:
    response = client.get("/api/v1/symbols")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "AAPL"
    assert body[0]["asset_type"] == "EQUITY"


def test_get_symbol_bars_resolves_to_latest_fetch(client: TestClient) -> None:
    response = client.get(
        "/api/v1/symbols/AAPL/bars", params={"start": "2026-06-01", "end": "2026-07-31"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["as_of"] == "2026-07-01"
    # Numeric(18, 6) column -> consistent 6-decimal-place string; the later
    # fetch's close, not the earlier one.
    assert body[0]["close"] == "100.250000"


def test_get_symbol_bars_unknown_ticker_404s(client: TestClient) -> None:
    response = client.get("/api/v1/symbols/ZZZZ/bars")
    assert response.status_code == 404


def test_get_symbol_indicators_defaults_to_latest_as_of(client: TestClient) -> None:
    response = client.get("/api/v1/symbols/AAPL/indicators")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["indicator_name"] == "SMA_20"
    assert body[0]["value"] == "99.750000"
