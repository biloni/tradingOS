"""`/api/v1/backtests` endpoint tests run against an in-memory SQLite
database with a hand-authored PriceBar+Indicator fixture across a short
window — no live Postgres, per the project's fixtures-not-live-APIs test
policy (same pattern as test_symbols_endpoints.py)."""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
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
from tradingos_api.models.strategy_version import StrategyVersion
from tradingos_api.models.symbol import AssetType, Symbol

D0 = date(2026, 1, 5)


def _dates(n: int) -> list[date]:
    return [D0 + timedelta(days=i) for i in range(n)]


def _add_bar(session: Session, symbol_id: int, as_of: date, open_: Decimal, close: Decimal) -> None:
    session.add(
        PriceBar(
            symbol_id=symbol_id,
            as_of=as_of,
            timeframe=Timeframe.DAY,
            open=open_,
            high=max(open_, close),
            low=min(open_, close),
            close=close,
            volume=1000,
            source="test",
            adjustment="split",
            fetched_at=datetime.now(UTC),
        )
    )


def _add_indicators(
    session: Session,
    symbol_id: int,
    as_of: date,
    *,
    sma_20: Decimal,
    sma_50: Decimal,
    rsi_14: Decimal,
    macd_line: Decimal,
    macd_signal: Decimal,
    bb_mid: Decimal,
) -> None:
    computed_at = datetime.now(UTC)
    for name, value in [
        (IndicatorName.SMA_20, sma_20),
        (IndicatorName.SMA_50, sma_50),
        (IndicatorName.RSI_14, rsi_14),
        (IndicatorName.MACD_LINE, macd_line),
        (IndicatorName.MACD_SIGNAL, macd_signal),
        (IndicatorName.BB_MID, bb_mid),
    ]:
        session.add(
            Indicator(
                symbol_id=symbol_id,
                as_of=as_of,
                indicator_name=name,
                version="v1",
                value=value,
                computed_at=computed_at,
            )
        )


def _seed_bullish_round_trip(session: Session, symbol_id: int, dates: list[date]) -> None:
    """day0 neutral; day1 bullish (queues an entry, fills day2); the rest
    stay neutral so the resulting position holds to end-of-window."""
    for i, d in enumerate(dates):
        if i == 1:
            _add_bar(session, symbol_id, d, Decimal(100), Decimal(105))
            _add_indicators(
                session,
                symbol_id,
                d,
                sma_20=Decimal(110),
                sma_50=Decimal(100),
                rsi_14=Decimal(60),
                macd_line=Decimal(2),
                macd_signal=Decimal(1),
                bb_mid=Decimal(100),
            )
        else:
            _add_bar(session, symbol_id, d, Decimal(100 + i), Decimal(100))
            _add_indicators(
                session,
                symbol_id,
                d,
                sma_20=Decimal(100),
                sma_50=Decimal(100),
                rsi_14=Decimal(40),
                macd_line=Decimal(1),
                macd_signal=Decimal(1),
                bb_mid=Decimal(100),
            )


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

    aapl = Symbol(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
        active=True,
    )
    # Marked inactive *today* on purpose — the backtest must still include
    # its historical series (ADR-025's survivorship-bias mitigation), never
    # filtering the universe by the current `active` flag.
    oldco = Symbol(
        ticker="OLDCO",
        name="Old Company Inc.",
        exchange="NYSE",
        asset_type=AssetType.EQUITY,
        active=False,
    )
    session.add_all([aapl, oldco])
    session.commit()
    session.refresh(aapl)
    session.refresh(oldco)

    dates = _dates(6)
    _seed_bullish_round_trip(session, aapl.id, dates)
    _seed_bullish_round_trip(session, oldco.id, dates)
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


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "date_range_start": D0.isoformat(),
        "date_range_end": (D0 + timedelta(days=5)).isoformat(),
        "benchmark_ticker": None,
    }
    body.update(overrides)
    return body


class TestCreateBacktest:
    def test_runs_over_the_seeded_window_and_persists(self, client: TestClient) -> None:
        response = client.post("/api/v1/backtests", json=_body())
        assert response.status_code == 201
        body = response.json()
        assert body["date_range_start"] == D0.isoformat()
        assert len(body["results_summary"]["equity_curve"]) == 6
        assert body["results_summary"]["num_trades"] >= 1

    def test_survivorship_bias_mitigation_includes_inactive_symbol(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/v1/backtests", json=_body())
        body = response.json()
        tickers_traded = {t["ticker"] for t in body["results_summary"]["trades"]}
        assert "OLDCO" in tickers_traded

    def test_defaults_to_the_full_ingested_window_when_dates_omitted(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/backtests", json=_body(date_range_start=None, date_range_end=None)
        )
        assert response.status_code == 201
        assert response.json()["results_summary"]["num_trades"] >= 1

    def test_unknown_strategy_version_id_is_a_400(self, client: TestClient) -> None:
        response = client.post("/api/v1/backtests", json=_body(strategy_version_id=9999))
        assert response.status_code == 400

    def test_no_price_history_in_range_is_a_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/backtests",
            json=_body(date_range_start="2000-01-01", date_range_end="2000-01-02"),
        )
        assert response.status_code == 400

    def test_explicit_strategy_version_id_is_honored(
        self, client: TestClient, db_session: Session
    ) -> None:
        neutral_strategy = StrategyVersion(
            name="all-zero-weights",
            config={"weights": {"trend": 0, "momentum": 0, "macd": 0, "bollinger": 0}},
            is_active=False,
            created_at=datetime.now(UTC),
        )
        db_session.add(neutral_strategy)
        db_session.commit()
        db_session.refresh(neutral_strategy)

        response = client.post(
            "/api/v1/backtests", json=_body(strategy_version_id=neutral_strategy.id)
        )

        assert response.status_code == 201
        body = response.json()
        assert body["strategy_version_id"] == neutral_strategy.id
        # All-zero weights -> compute_score always returns the neutral 50,
        # which never crosses the entry threshold -> zero trades.
        assert body["results_summary"]["num_trades"] == 0

    def test_benchmark_ticker_not_tracked_is_null_not_an_error(self, client: TestClient) -> None:
        response = client.post("/api/v1/backtests", json=_body(benchmark_ticker="SPY"))
        assert response.status_code == 201
        assert response.json()["results_summary"]["benchmark_return_pct"] is None


class TestListAndGet:
    def test_list_and_get_roundtrip(self, client: TestClient) -> None:
        created = client.post("/api/v1/backtests", json=_body()).json()

        list_response = client.get("/api/v1/backtests")
        assert list_response.status_code == 200
        assert any(r["id"] == created["id"] for r in list_response.json())

        get_response = client.get(f"/api/v1/backtests/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == created["id"]

    def test_unknown_id_404s(self, client: TestClient) -> None:
        response = client.get("/api/v1/backtests/999999")
        assert response.status_code == 404
