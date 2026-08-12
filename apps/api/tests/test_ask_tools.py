"""`services/ask_tools.py` — the schema-validated dispatcher `/api/v1/ask`
calls. Against the real `db_session` fixture (rolled back after each
test), with fixtures built inside the test's own transaction rather
than relying on seed/live data, so these stay deterministic regardless
of what a live committee run has since written to the shared dev DB.
No LLM involved — this module never touches the network."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AssetType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    RecommendationStatus,
)
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.ask_tools import (
    GetRecommendationsArgs,
    GetUpcomingEarningsArgs,
    QueryInstrumentsArgs,
    UnknownToolError,
    execute_tool,
)


@pytest.fixture
def instrument(db_session: Session) -> Instrument:
    inst = Instrument(
        ticker=f"ASK{uuid.uuid4().hex[:6].upper()}",
        name="Ask Tools Test Co",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
        active=True,
    )
    db_session.add(inst)
    db_session.flush()
    return inst


@pytest.fixture
def recommendation_with_version(
    db_session: Session, instrument: Instrument
) -> tuple[Recommendation, RecommendationVersion]:
    rec = Recommendation(
        instrument_id=instrument.id,
        mode=RecommendationMode.INVESTMENT,
        opened_at=datetime.now(UTC),
        status=RecommendationStatus.ACTIVE,
    )
    db_session.add(rec)
    db_session.flush()
    version = RecommendationVersion(
        recommendation_id=rec.id,
        version_number=1,
        action=RecommendationAction.BUY,
        lane_action="INVEST_WATCH",
        confidence=RecommendationConfidence.MEDIUM,
        score=Decimal("62.50"),
        rationale="Test rationale grounded in fixture evidence.",
        generated_at=datetime.now(UTC),
    )
    db_session.add(version)
    db_session.flush()
    return rec, version


class TestQueryInstruments:
    def test_filters_by_ticker(self, db_session: Session, instrument: Instrument) -> None:
        args = QueryInstrumentsArgs(tickers=[instrument.ticker])
        result = execute_tool(db_session, "query_instruments", args.model_dump())
        tickers = [row["ticker"] for row in result.output["instruments"]]
        assert tickers == [instrument.ticker]

    def test_no_filter_does_not_error(self, db_session: Session, instrument: Instrument) -> None:
        result = execute_tool(db_session, "query_instruments", {})
        tickers = [row["ticker"] for row in result.output["instruments"]]
        assert instrument.ticker in tickers


class TestGetRecommendations:
    def test_returns_latest_version_fields(
        self,
        db_session: Session,
        instrument: Instrument,
        recommendation_with_version: tuple[Recommendation, RecommendationVersion],
    ) -> None:
        rec, _version = recommendation_with_version
        result = execute_tool(
            db_session,
            "get_recommendations",
            GetRecommendationsArgs(ticker=instrument.ticker).model_dump(),
        )
        rows = result.output["recommendations"]
        assert len(rows) == 1
        assert rows[0]["recommendation_id"] == str(rec.id)
        assert rows[0]["ticker"] == instrument.ticker
        assert rows[0]["lane_action"] == "INVEST_WATCH"
        assert rows[0]["confidence"] == "MEDIUM"
        assert rows[0]["score"] == "62.50"
        assert len(result.recommendation_summaries) == 1
        assert result.recommendation_summaries[0].recommendation_id == rec.id

    def test_unknown_ticker_is_a_tool_error_not_a_crash(self, db_session: Session) -> None:
        result = execute_tool(
            db_session, "get_recommendations", GetRecommendationsArgs(ticker="NOPE").model_dump()
        )
        assert "error" in result.output
        assert result.recommendation_summaries == []

    def test_mode_filter_excludes_the_other_lane(
        self,
        db_session: Session,
        instrument: Instrument,
        recommendation_with_version: tuple[Recommendation, RecommendationVersion],
    ) -> None:
        result = execute_tool(
            db_session,
            "get_recommendations",
            GetRecommendationsArgs(ticker=instrument.ticker, mode="TACTICAL").model_dump(),
        )
        assert result.output["recommendations"] == []

    def test_invalid_mode_is_a_tool_error_not_a_crash(
        self, db_session: Session, instrument: Instrument
    ) -> None:
        result = execute_tool(
            db_session,
            "get_recommendations",
            GetRecommendationsArgs(ticker=instrument.ticker, mode="NOT_A_MODE").model_dump(),
        )
        assert "error" in result.output


class TestGetUpcomingEarnings:
    def test_returns_events_within_the_window(
        self, db_session: Session, instrument: Instrument
    ) -> None:
        event = EarningsEvent(
            instrument_id=instrument.id,
            fiscal_period="Q3",
            report_date=date.today() + timedelta(days=5),
            eps_estimate=Decimal("1.35"),
            source="test-fixture",
        )
        db_session.add(event)
        db_session.flush()

        result = execute_tool(
            db_session, "get_upcoming_earnings", GetUpcomingEarningsArgs(days=14).model_dump()
        )
        tickers = [row["ticker"] for row in result.output["events"]]
        assert instrument.ticker in tickers

    def test_excludes_events_outside_the_window(
        self, db_session: Session, instrument: Instrument
    ) -> None:
        event = EarningsEvent(
            instrument_id=instrument.id,
            report_date=date.today() + timedelta(days=90),
            source="test-fixture",
        )
        db_session.add(event)
        db_session.flush()

        result = execute_tool(
            db_session, "get_upcoming_earnings", GetUpcomingEarningsArgs(days=14).model_dump()
        )
        tickers = [row["ticker"] for row in result.output["events"]]
        assert instrument.ticker not in tickers

    def test_unknown_ticker_filter_is_a_tool_error_not_a_crash(self, db_session: Session) -> None:
        result = execute_tool(
            db_session, "get_upcoming_earnings", GetUpcomingEarningsArgs(ticker="NOPE").model_dump()
        )
        assert "error" in result.output


class TestUnknownTool:
    def test_unknown_tool_name_raises(self, db_session: Session) -> None:
        with pytest.raises(UnknownToolError):
            execute_tool(db_session, "delete_everything", {})
