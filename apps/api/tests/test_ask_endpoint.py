"""`POST /api/v1/ask` (ADR-019) — the tool-use loop, rate limit, and
graceful degradation, all against a fake `LLMProvider` overridden via
`app.dependency_overrides` (per `core/dependencies.py::get_llm_provider`'s
own docstring). No network call, no real Anthropic spend — live
verification against the real API lives in
`docs/TEST_EVIDENCE.md`'s end-to-end platform testing entry, not here."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import ask_rate_limiter
from tradingos_api.main import app
from tradingos_api.models.enums import (
    AssetType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
    RecommendationStatus,
)
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.llm import LLMResponse, LLMToolCall


def _seed_recommendation(db_session: Session) -> tuple[Instrument, Recommendation]:
    inst = Instrument(
        ticker="ASKEP1", name="Ask Endpoint Test Co", exchange="NASDAQ", asset_type=AssetType.EQUITY
    )
    db_session.add(inst)
    db_session.flush()
    rec = Recommendation(
        instrument_id=inst.id,
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
        score=Decimal("55.00"),
        rationale="Seeded for endpoint test.",
        generated_at=datetime.now(UTC),
    )
    db_session.add(version)
    db_session.flush()
    return inst, rec


class _OneToolCallThenAnswerLLM:
    """First call: asks for `get_recommendations`. Second call: answers
    in plain text using the tool result already fed back to it."""

    def __init__(self, ticker: str) -> None:
        self._ticker = ticker
        self._call_count = 0

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> LLMResponse:
        self._call_count += 1
        if self._call_count == 1:
            return LLMResponse(
                prompt_version=prompt_version,
                model="claude-sonnet-5",
                stop_reason="tool_use",
                text=None,
                tool_calls=[
                    LLMToolCall(
                        tool_use_id="t1",
                        tool_name="get_recommendations",
                        arguments={"ticker": self._ticker},
                    )
                ],
                raw_content=[{"type": "tool_use", "id": "t1", "name": "get_recommendations"}],
                input_tokens=200,
                output_tokens=40,
            )
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text=f"{self._ticker} is currently INVEST_WATCH at MEDIUM confidence.",
            tool_calls=[],
            raw_content=[{"type": "text", "text": "answer"}],
            input_tokens=300,
            output_tokens=25,
        )


class _NoToolCallLLM:
    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            prompt_version="ask-v1",
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="I don't have anything to look up for that.",
            tool_calls=[],
            raw_content=[{"type": "text", "text": "answer"}],
            input_tokens=100,
            output_tokens=15,
        )


class _AlwaysToolCallLLM:
    """Never stops calling the same tool — used to prove the
    `MAX_ITERATIONS` cap actually bounds the loop."""

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[LLMToolCall(tool_use_id="t1", tool_name="query_instruments", arguments={})],
            raw_content=[{"type": "tool_use", "id": "t1", "name": "query_instruments"}],
            input_tokens=100,
            output_tokens=20,
        )


def _override_llm(fake_llm: Any) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm


class TestAskEndpoint:
    def test_answers_using_a_real_tool_result(
        self, client: TestClient, db_session: Session
    ) -> None:
        inst, _rec = _seed_recommendation(db_session)
        ask_rate_limiter.reset()
        _override_llm(_OneToolCallThenAnswerLLM(inst.ticker))
        try:
            question = f"What's the call on {inst.ticker}?"
            response = client.post("/api/v1/ask", json={"question": question})
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)

        assert response.status_code == 200, response.text
        body = response.json()
        assert inst.ticker in body["answer"]
        assert len(body["recommendations"]) == 1
        assert body["recommendations"][0]["ticker"] == inst.ticker
        assert body["recommendations"][0]["lane_action"] == "INVEST_WATCH"
        assert body["iterations"] == 2
        assert len(body["model_call_record_ids"]) == 2

    def test_answers_without_a_tool_call(self, client: TestClient) -> None:
        ask_rate_limiter.reset()
        _override_llm(_NoToolCallLLM())
        try:
            response = client.post("/api/v1/ask", json={"question": "Hi"})
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recommendations"] == []
        assert body["iterations"] == 1

    def test_loop_is_capped_at_max_iterations(self, client: TestClient) -> None:
        ask_rate_limiter.reset()
        _override_llm(_AlwaysToolCallLLM())
        try:
            response = client.post("/api/v1/ask", json={"question": "Keep going forever"})
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["iterations"] == 5
        assert "tool-call budget" in body["answer"]
        assert len(body["model_call_record_ids"]) == 5

    def test_blank_question_is_rejected(self, client: TestClient) -> None:
        ask_rate_limiter.reset()
        response = client.post("/api/v1/ask", json={"question": ""})
        assert response.status_code == 422

    def test_rate_limit_returns_429(self, client: TestClient) -> None:
        ask_rate_limiter.reset()
        _override_llm(_NoToolCallLLM())
        try:
            for _ in range(5):
                ok_response = client.post("/api/v1/ask", json={"question": "Hi"})
                assert ok_response.status_code == 200
            limited_response = client.post("/api/v1/ask", json={"question": "Hi"})
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)
            ask_rate_limiter.reset()

        assert limited_response.status_code == 429

    def test_no_api_key_degrades_to_503_not_a_crash(self, client: TestClient) -> None:
        from tradingos_api.providers.llm import LLMProviderNotConfigured

        def _raise_not_configured() -> Any:
            raise LLMProviderNotConfigured("ANTHROPIC_API_KEY is not set.")

        ask_rate_limiter.reset()

        from fastapi import HTTPException

        def _override() -> Any:
            try:
                _raise_not_configured()
            except LLMProviderNotConfigured as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        app.dependency_overrides[get_llm_provider] = _override
        try:
            response = client.post("/api/v1/ask", json={"question": "Hi"})
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)

        assert response.status_code == 503
