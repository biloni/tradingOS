"""services/ask.py's tool-use orchestration loop is tested against a fake
LLMProvider that scripts a fixed sequence of responses — no real Anthropic
call, per the project's fixtures-not-live-APIs test policy."""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingos_api.db.base import Base
from tradingos_api.models.indicator import Indicator, IndicatorName
from tradingos_api.models.llm_call_log import LLMCallLog
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.symbol import AssetType, Symbol
from tradingos_api.providers.llm import LLMResponse, LLMToolCall
from tradingos_api.services.ask import MAX_ITERATIONS, answer_question

# Relative to "today" so compute_recommendation's lookback window sees this
# data regardless of when the suite runs.
PRICE_DATE = date.today() - timedelta(days=1)
FETCHED_AT = datetime.now(UTC) - timedelta(days=1)


class ScriptedLLMProvider:
    """Returns each response in `responses` in order, one per `complete()`
    call — lets a test dictate exactly what the model "says" each turn."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self.calls = 0

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        response = self._responses[self.calls]
        self.calls += 1
        return response


class AlwaysToolUseLLMProvider:
    """Never produces a final answer — used to verify the iteration cap."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(tool_use_id=f"t{self.calls}", tool_name="query_symbols", arguments={})
            ],
            raw_content=[
                {"type": "tool_use", "id": f"t{self.calls}", "name": "query_symbols", "input": {}}
            ],
            input_tokens=50,
            output_tokens=10,
        )


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
    db.commit()

    try:
        yield db
    finally:
        db.close()


def _tool_use_response(tool_name: str, arguments: dict[str, object]) -> LLMResponse:
    return LLMResponse(
        prompt_version="ask-v1",
        model="claude-sonnet-5",
        stop_reason="tool_use",
        text=None,
        tool_calls=[LLMToolCall(tool_use_id="t1", tool_name=tool_name, arguments=arguments)],
        raw_content=[{"type": "tool_use", "id": "t1", "name": tool_name, "input": arguments}],
        input_tokens=100,
        output_tokens=20,
    )


def _final_text_response(text: str) -> LLMResponse:
    return LLMResponse(
        prompt_version="ask-v1",
        model="claude-sonnet-5",
        stop_reason="end_turn",
        text=text,
        tool_calls=[],
        raw_content=[{"type": "text", "text": text}],
        input_tokens=150,
        output_tokens=30,
    )


class TestToolCallThenFinalAnswer:
    def test_two_turn_flow_persists_recommendation_and_logs_both_calls(
        self, session: Session
    ) -> None:
        llm = ScriptedLLMProvider(
            [
                _tool_use_response("compute_recommendation", {"ticker": "AAPL"}),
                _final_text_response("AAPL scores well right now."),
            ]
        )

        result = answer_question(session, llm, "What does AAPL's setup look like?")

        assert result.answer == "AAPL scores well right now."
        assert result.iterations == 2
        assert len(result.recommendations) == 1
        assert result.recommendations[0].symbol_ticker == "AAPL"
        assert len(result.llm_call_log_ids) == 2

        logs = session.query(LLMCallLog).order_by(LLMCallLog.id).all()
        assert len(logs) == 2
        assert logs[0].input_tokens == 100
        assert logs[1].input_tokens == 150
        assert all(log.model == "claude-sonnet-5" for log in logs)
        assert all(log.cost_usd > 0 for log in logs)


class TestUnknownToolIsHandledGracefully:
    def test_error_tool_result_does_not_crash_the_loop(self, session: Session) -> None:
        llm = ScriptedLLMProvider(
            [
                _tool_use_response("delete_everything", {}),
                _final_text_response("I couldn't run that, here's what I know instead."),
            ]
        )

        result = answer_question(session, llm, "do something weird")

        assert result.answer == "I couldn't run that, here's what I know instead."
        assert result.iterations == 2

        logs = session.query(LLMCallLog).order_by(LLMCallLog.id).all()
        second_request = logs[1].request_payload
        tool_result_message = second_request["messages"][-1]
        assert tool_result_message["content"][0]["is_error"] is True


class TestIterationCap:
    def test_stops_at_max_iterations_and_returns_a_fallback_message(self, session: Session) -> None:
        llm = AlwaysToolUseLLMProvider()

        result = answer_question(session, llm, "never stop asking")

        assert result.iterations == MAX_ITERATIONS
        assert llm.calls == MAX_ITERATIONS
        assert len(result.llm_call_log_ids) == MAX_ITERATIONS
        assert "tool-call budget" in result.answer
