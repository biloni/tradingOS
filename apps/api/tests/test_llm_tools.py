"""services/llm_tools.py's dispatcher is tested against an in-memory
SQLite database — no live Postgres, per the project's fixtures-not-live-APIs
test policy (same pattern as test_symbols_endpoints.py)."""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingos_api.db.base import Base
from tradingos_api.models.indicator import Indicator, IndicatorName
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.recommendation import Recommendation, RecommendationStatus
from tradingos_api.models.symbol import AssetType, Symbol
from tradingos_api.services.llm_tools import UnknownToolError, execute_tool

# Relative to "today" so the lookback-window tools (get_price_summary,
# compute_recommendation) see this data regardless of when the suite runs.
PRICE_DATE = date.today() - timedelta(days=1)
FETCHED_AT = datetime.now(UTC) - timedelta(days=1)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    db = TestSessionLocal()

    symbol = Symbol(
        ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", asset_type=AssetType.EQUITY
    )
    db.add(symbol)
    db.commit()
    db.refresh(symbol)

    db.add(
        PriceBar(
            symbol_id=symbol.id,
            as_of=PRICE_DATE,
            timeframe=Timeframe.DAY,
            open=99.0,
            high=100.0,
            low=98.5,
            close=99.5,
            volume=1000,
            source="alpaca",
            adjustment="split",
            fetched_at=FETCHED_AT,
        )
    )
    db.add(
        Indicator(
            symbol_id=symbol.id,
            as_of=PRICE_DATE,
            indicator_name=IndicatorName.SMA_20,
            version="v1",
            value=95.0,
            computed_at=FETCHED_AT,
        )
    )
    db.add(
        Indicator(
            symbol_id=symbol.id,
            as_of=PRICE_DATE,
            indicator_name=IndicatorName.SMA_50,
            version="v1",
            value=90.0,
            computed_at=FETCHED_AT,
        )
    )
    db.commit()

    try:
        yield db
    finally:
        db.close()


class TestQuerySymbols:
    def test_no_filter_returns_all(self, session: Session) -> None:
        result = execute_tool(session, "query_symbols", {})
        assert [s["ticker"] for s in result.output["symbols"]] == ["AAPL"]

    def test_ticker_filter(self, session: Session) -> None:
        result = execute_tool(session, "query_symbols", {"tickers": ["ZZZZ"]})
        assert result.output["symbols"] == []

    def test_invalid_asset_type_returns_error_not_crash(self, session: Session) -> None:
        result = execute_tool(session, "query_symbols", {"asset_type": "BOND"})
        assert "error" in result.output


class TestGetPriceSummary:
    def test_success(self, session: Session) -> None:
        result = execute_tool(session, "get_price_summary", {"ticker": "aapl"})
        assert result.output["ticker"] == "AAPL"
        assert result.output["latest_close"] == "99.500000"

    def test_unknown_ticker_returns_error(self, session: Session) -> None:
        result = execute_tool(session, "get_price_summary", {"ticker": "ZZZZ"})
        assert "error" in result.output


class TestGetIndicators:
    def test_success(self, session: Session) -> None:
        result = execute_tool(session, "get_indicators", {"ticker": "AAPL"})
        assert result.output["indicators"]["SMA_20"] == "95.000000"
        assert result.output["indicators"]["SMA_50"] == "90.000000"

    def test_no_indicators_returns_error(self, session: Session) -> None:
        result = execute_tool(session, "get_price_summary", {"ticker": "AAPL"})
        assert "error" not in result.output  # sanity: price summary unaffected
        result2 = execute_tool(session, "get_indicators", {"ticker": "ZZZZ"})
        assert "error" in result2.output


class TestGetRecommendations:
    def test_empty_initially(self, session: Session) -> None:
        result = execute_tool(session, "get_recommendations", {})
        assert result.output["recommendations"] == []

    def test_invalid_status_returns_error(self, session: Session) -> None:
        result = execute_tool(session, "get_recommendations", {"status": "BOGUS"})
        assert "error" in result.output


class TestComputeRecommendation:
    def test_persists_a_recommendation_and_returns_draft(self, session: Session) -> None:
        result = execute_tool(session, "compute_recommendation", {"ticker": "AAPL"})
        assert "recommendation_id" in result.output
        assert result.recommendation_draft is not None
        assert result.recommendation_draft.symbol_ticker == "AAPL"

        rows = session.query(Recommendation).all()
        assert len(rows) == 1
        assert rows[0].status == RecommendationStatus.ACTIVE

    def test_recomputing_supersedes_the_prior_active_row(self, session: Session) -> None:
        execute_tool(session, "compute_recommendation", {"ticker": "AAPL"})
        execute_tool(session, "compute_recommendation", {"ticker": "AAPL"})

        rows = session.query(Recommendation).order_by(Recommendation.id).all()
        assert len(rows) == 2
        assert rows[0].status == RecommendationStatus.SUPERSEDED
        assert rows[1].status == RecommendationStatus.ACTIVE

    def test_unknown_ticker_returns_error_without_persisting(self, session: Session) -> None:
        result = execute_tool(session, "compute_recommendation", {"ticker": "ZZZZ"})
        assert "error" in result.output
        assert session.query(Recommendation).count() == 0


class TestDispatchValidation:
    def test_unknown_tool_raises(self, session: Session) -> None:
        with pytest.raises(UnknownToolError):
            execute_tool(session, "delete_everything", {})

    def test_missing_required_argument_raises_validation_error(self, session: Session) -> None:
        with pytest.raises(ValidationError):
            execute_tool(session, "get_indicators", {})
